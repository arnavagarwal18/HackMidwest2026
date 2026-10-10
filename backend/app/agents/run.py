"""run_feedback: build and save a take's feedback record and practice plan, using the rule plan on any failure.

Only the fallback exists so far. When AI is on and the Orchestrator isn't built yet, the run falls back
with reason 'model_error' and says so in the log and the trace.
"""
import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from app import store
from app.agents.config import get_settings
from app.agents.fallback import build_fallback
from app.agents.trace import Trace
from app.errors import AppError
from app.takes.pipeline_steps import resolve_step
from app.takes.take_store import update_take

log = logging.getLogger(__name__)

TIME_LIMIT_S = 30  # for the agents, once they exist; the rule plan takes milliseconds
_run_locks: dict[tuple[str, str], threading.Lock] = {}
_registry_lock = threading.Lock()
_numbering_lock = threading.Lock()  # feedback, plan and exercise ids are numbered and saved under this lock


@contextmanager
def _exclusive(session_id: str, take_id: str, wait: bool):
    """One feedback run per take at a time; without `wait`, a second caller gets 409 instead of queueing."""
    with _registry_lock:
        lock = _run_locks.setdefault((session_id, take_id), threading.Lock())
    if not lock.acquire(blocking=wait):
        raise AppError(409, "wrong_state", "Feedback already running.")
    try:
        yield
    finally:
        lock.release()


def ai_enabled() -> bool:
    return get_settings().ai_enabled


def _fallback_reason(cant_tell: bool, trace: Trace) -> str:
    if cant_tell:
        return "cant_tell"
    try:
        enabled = ai_enabled()
    except Exception:
        log.exception("Could not read the AI settings; using the rule plan")
        trace.add("orchestrator", "fallback", "model_error", "AI settings could not be read")
        return "model_error"
    if not enabled:
        return "disabled"
    log.error("AI is enabled but the Orchestrator isn't built yet; using the rule plan with reason model_error")
    trace.add("orchestrator", "fallback", "model_error", "no orchestrator available")
    return "model_error"


def _earlier_takes(takes: dict[str, dict], take: dict) -> list[dict]:
    """Earlier diagnosed takes on the same bars, in the shape the Checker's history uses."""
    return [
        {"take_id": t["take_id"], "error_rate": t["diagnosis"].get("error_rate"), "played_bpm": t["diagnosis"].get("played_bpm")}
        for t in takes.values()
        if isinstance(t.get("diagnosis"), dict) and (t["bar_from"], t["bar_to"]) == (take["bar_from"], take["bar_to"])
        and int(t["take_id"][1:]) < int(take["take_id"][1:])
    ]


def _build_records(session_id: str, take_id: str, trace: Trace, started: float) -> tuple[dict, dict]:
    """The numbered Feedback and Plan records for a take, not yet saved."""
    session = store.get(session_id)
    take = session.takes[take_id]
    diagnosis = take.get("diagnosis")
    if not isinstance(diagnosis, dict):
        log.warning("Take %s/%s has no diagnosis; its feedback will have no sentences", session_id, take_id)
        diagnosis = {}
    flags = {f["id"]: f for f in (take.get("form") or {}).get("flags") or []}
    try:
        fallback = build_fallback(diagnosis, take, _earlier_takes(session.takes, take), flags)
        reason = _fallback_reason(fallback.cant_tell, trace)
    except Exception:
        log.exception("The rule plan for take %s/%s failed; using a plain whole-range plan", session_id, take_id)
        trace.add("orchestrator", "fallback", "model_error", "rule plan failed")
        fallback, reason = build_fallback({}, take, [], {}), "model_error"
    feedback_id, plan_id = f"fb{len(session.feedback) + 1}", f"pl{len(session.plans) + 1}"
    first_exercise = 1 + sum(len(p["exercises"]) for p in session.plans.values())
    exercises = [{"id": f"ex{first_exercise + i}", **ex} for i, ex in enumerate(fallback.exercises)]
    trace.add("orchestrator", "fallback", reason, f"rule plan with {len(exercises)} exercises")
    feedback = {
        "id": feedback_id, "take_id": take_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "fallback", "fallback_reason": reason, "cant_tell": fallback.cant_tell,
        "tier1": diagnosis.get("tier1") or [], "sentences": fallback.sentences, "dropped": [], "plan_id": plan_id,
        "check": {"coach_tries": 0, "planner_tries": 0, "claims_checked": 0, "claims_failed": 0, "sentences_dropped": 0},
        "duration_ms": round((time.monotonic() - started) * 1000),
    }
    plan = {"id": plan_id, "take_id": take_id, "feedback_id": feedback_id, "mode": "fallback", "exercises": exercises}
    return feedback, plan


def _create_records(session_id: str, take_id: str, trace: Trace, started: float) -> tuple[dict, dict]:
    """Number and save the records. The plan goes first, so a saved feedback never points at a missing plan."""
    with _numbering_lock:
        feedback, plan = _build_records(session_id, take_id, trace, started)
        session = store.get(session_id)
        store.update(session_id, "plans", {**session.plans, plan["id"]: plan})
        store.update(session_id, "feedback", {**session.feedback, feedback["id"]: feedback})
    return feedback, plan


def _init_practice(session_id: str, plan_id: str) -> None:
    try:
        init_plan = resolve_step("app.practice", "init_plan")
        if init_plan is None:
            return
        init_plan(session_id, plan_id)
    except Exception:
        log.exception("practice.init_plan failed for plan %s/%s", session_id, plan_id)


def _fail_take(session_id: str, take_id: str) -> None:
    try:
        update_take(session_id, take_id, status="failed", error="storage_error")
    except Exception:
        log.exception("Could not mark take %s/%s as failed", session_id, take_id)


def run_feedback(session_id: str, take_id: str, *, wait: bool = True) -> str | None:
    """Create the take's feedback record and plan and return the feedback id.

    No failure of the run itself raises: the rule plan is used instead. If even that can't be saved, the take
    is marked failed (storage_error) and None is returned. With wait=False, a run already in progress for
    the take raises AppError 409 'Feedback already running.'; with wait=True it queues behind that run.
    """
    with _exclusive(session_id, take_id, wait):
        started, trace = time.monotonic(), Trace()
        try:
            feedback, plan = _create_records(session_id, take_id, trace, started)
        except Exception:
            log.exception("Feedback for take %s/%s could not be saved", session_id, take_id)
            _fail_take(session_id, take_id)
            return None
        trace.save(store.session_dir(session_id) / f"{feedback['id']}_trace.json")
        _init_practice(session_id, plan["id"])
        return feedback["id"]
