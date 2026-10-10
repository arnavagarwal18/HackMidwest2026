"""The AI path of run_feedback: the Orchestrator, Coach and Planner under a time limit, never raising."""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.config import get_settings
from app.agents.context import CheckContext, build_context
from app.agents.holder import RunHolder
from app.agents.model import build_agent_model
from app.agents.orchestrator import build_orchestrator
from app.agents.tools import make_tools
from app.agents.trace import Trace

log = logging.getLogger(__name__)

TIME_LIMIT_S = 30
ORCHESTRATOR_REQUEST = "Feedback for take {take_id}. Read the overview first."


@dataclass
class AiFeedback:
    """What the AI path produced.

    `sentences` is None when the Coach's output can't be shown, and `reason` then says why.
    `exercises` is None when the Planner's output can't be used (the rule plan is used instead); each exercise has no id yet.
    """

    sentences: list[dict] | None
    dropped: list[dict] = field(default_factory=list)
    check: dict = field(default_factory=dict)
    reason: str | None = None
    exercises: list[dict] | None = None
    error_class: str | None = None  # the class (never the message) of the error that stopped the run or an agent in it


def new_model() -> Any:
    return build_agent_model(get_settings())


def context_and_tools(session_id: str, take: dict, history: list[dict]) -> tuple[CheckContext, dict]:
    sources = {
        "get_diagnosis": lambda s, t: take.get("diagnosis"),
        "get_form": lambda s, t: take.get("form") or {},
        "get_earlier_takes": lambda s, t: history,
    }
    return build_context(session_id, take["take_id"], **sources), make_tools(session_id, take["take_id"], **sources)


async def _run(session_id: str, take: dict, history: list[dict], holder: RunHolder, trace: Trace) -> None:
    ctx, tools = context_and_tools(session_id, take, history)
    orchestrator = build_orchestrator(new_model(), tools, ctx, holder, trace)
    await asyncio.wait_for(orchestrator.invoke_async(ORCHESTRATOR_REQUEST.format(take_id=take["take_id"])), TIME_LIMIT_S)


def shown_sentence(sentence: dict) -> dict:
    jump = sentence.get("jump") or {}
    return {"text": sentence["text"], "cites": sentence["cites"], "claims": sentence.get("claims") or [],
            "jump": {"bar": jump.get("bar"), "time_s": jump.get("time_s")}, "checked": True, "mode": "ai"}


def _failure_reason(holder: RunHolder, failure: BaseException | None) -> str:
    if isinstance(failure, asyncio.TimeoutError):
        return "timeout"
    if failure is not None or holder.errors or holder.coach_tries == 0:
        return "model_error"
    return "checker_rejected"


def _error_class(holder: RunHolder, failure: BaseException | None) -> str | None:
    errors = [failure] if failure is not None else [*holder.errors, *holder.planner_errors]
    return type(errors[0]).__name__ if errors else None


def _accepted_exercises(session_id: str, take: dict, holder: RunHolder) -> list[dict] | None:
    if holder.plan is not None:
        return holder.plan["exercises"]
    log.error("No Planner plan for take %s/%s (planner tries %s, errors %s)", session_id, take["take_id"],
              holder.planner_tries, [type(e).__name__ for e in holder.planner_errors])
    return None


def run_ai_feedback(session_id: str, take: dict, history: list[dict], trace: Trace, cant_tell: bool = False) -> AiFeedback:
    """Run the agents on a diagnosed take. Anything the Coach or Planner got accepted is kept, even if a later step failed.

    For a take that can't be judged only the Planner runs, so there are no sentences and no failure reason.
    """
    holder, failure = RunHolder(), None
    try:
        asyncio.run(_run(session_id, take, history, holder, trace))
    except Exception as exc:
        failure = exc
        log.exception("The feedback agents failed for take %s/%s (%s)", session_id, take["take_id"], type(exc).__name__)
    exercises = _accepted_exercises(session_id, take, holder)
    check, error_class = holder.check_counts(), _error_class(holder, failure)
    if cant_tell:
        return AiFeedback(None, check=check, exercises=exercises, error_class=error_class)
    if holder.feedback is not None:
        return AiFeedback([shown_sentence(s) for s in holder.feedback["sentences"]], holder.dropped, check, exercises=exercises, error_class=error_class)
    reason = _failure_reason(holder, failure)
    log.error("No Coach feedback for take %s/%s: %s", session_id, take["take_id"], reason)
    return AiFeedback(None, check=check, reason=reason, exercises=exercises, error_class=error_class)
