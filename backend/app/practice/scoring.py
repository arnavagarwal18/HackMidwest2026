"""score_rep: judge a processed rep take against its exercise's pass mark and move the tempo ladder."""
import logging
from typing import Any

from .. import store
from .progress import find_exercise, read_progress, update_progress
from .rules import judge_rep, step_ladder

logger = logging.getLogger("app.practice")

STATUS_SCORED = "scored"
STATUS_NOT_COUNTED = "not_counted"
STATUS_FAILED = "failed"
SCORING_FAILED_REASON = "scoring failed"
TAKE_FAILED = "failed"


def _rep_result(take: dict, state: dict | None, status: str, reasons: list[str], judged: dict | None = None) -> dict:
    """A RepResult; the ladder fields come from `state` (the ladder as it stands after this rep)."""
    judged = judged or {}
    state = state or {}
    return {
        "take_id": take["take_id"], "exercise_id": take.get("exercise_id"), "tempo_bpm": take.get("tempo_bpm"),
        "status": status, "passed": judged.get("passed"), "reasons": reasons,
        "errors": judged.get("errors"), "mean_abs_timing_ms": judged.get("mean_abs_timing_ms"),
        "form_flag_ids": judged.get("form_flag_ids", []),
        "next_bpm": state.get("current_bpm", take.get("tempo_bpm")), "streak": state.get("streak", 0),
        "exercise_complete": state.get("complete", False),
    }


def _record_unchanged_ladder(session_id: str, take: dict, status: str, reasons: list[str]) -> None:
    """Save a rep result that doesn't count: the exercise state is not touched."""
    def save(progress: dict) -> None:
        state = progress["exercises"].get(take.get("exercise_id"))
        progress["reps"][take["take_id"]] = _rep_result(take, state, status, reasons)
    update_progress(session_id, save)


def _cant_tell_reason(exercise: dict) -> str:
    return f"could not line up this rep with bars {exercise['bar_from']}-{exercise['bar_to']}"


def _judge(take: dict, exercise: dict) -> dict:
    flags = (take.get("form") or {}).get("flags") or []
    return judge_rep(exercise, take["diagnosis"], take["kind"], take.get("form_status", "none"), flags)


def _score_and_step(session_id: str, take: dict, exercise: dict, judged: dict) -> None:
    """Save the RepResult and the stepped ExerciseState in one update."""
    def save(progress: dict) -> None:
        exercise_id = exercise["id"]
        state = progress["exercises"][exercise_id]
        stepped = step_ladder(state, exercise, judged["passed"])
        if judged["passed"]:
            stepped["best_passed_bpm"] = max(state["best_passed_bpm"] or 0, take["tempo_bpm"])
        if take["take_id"] not in state["rep_ids"]:
            stepped["rep_ids"] = [*state["rep_ids"], take["take_id"]]
        progress["exercises"][exercise_id] = stepped
        progress["reps"][take["take_id"]] = _rep_result(take, stepped, STATUS_SCORED, judged["reasons"], judged)
    update_progress(session_id, save)


def _score(session_id: str, take_id: str) -> None:
    take = store.get(session_id).takes[take_id]
    if read_progress(session_id)["reps"].get(take_id, {}).get("status") == STATUS_SCORED:
        logger.info("Rep take %s/%s is already scored; leaving the ladder as it is", session_id, take_id)
        return
    if take["status"] == TAKE_FAILED:
        _record_unchanged_ladder(session_id, take, STATUS_FAILED, [take.get("error") or SCORING_FAILED_REASON])
        return
    exercise = find_exercise(session_id, take["exercise_id"])
    if exercise is None:
        raise LookupError(f"exercise {take['exercise_id']} is in no plan of session {session_id}")
    if take["diagnosis"].get("cant_tell"):
        _record_unchanged_ladder(session_id, take, STATUS_NOT_COUNTED, [_cant_tell_reason(exercise)])
        return
    _score_and_step(session_id, take, exercise, _judge(take, exercise))


def _record_scoring_failed(session_id: str, take_id: str) -> None:
    try:
        take: dict[str, Any] = store.get(session_id).takes[take_id]
        _record_unchanged_ladder(session_id, take, STATUS_FAILED, [SCORING_FAILED_REASON])
    except Exception:
        logger.exception("Could not record that scoring of rep take %s/%s failed", session_id, take_id)


def score_rep(session_id: str, take_id: str) -> None:
    """Score one rep take and save its RepResult and the exercise's new ladder state. Never raises.

    A failed take is 'failed' with its error, a can't-tell take is 'not_counted'; neither moves the ladder.
    Any unexpected error is logged with the take id and recorded as 'failed' / 'scoring failed', ladder unchanged.
    """
    try:
        _score(session_id, take_id)
    except Exception:
        logger.exception("Scoring rep take %s/%s failed", session_id, take_id)
        _record_scoring_failed(session_id, take_id)
