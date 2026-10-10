"""Feedback routes: read a take's latest feedback and plan, or run the feedback again."""
import logging

from fastapi import APIRouter

from app import store
from app.agents.run import run_feedback
from app.errors import AppError, storage_error

log = logging.getLogger(__name__)
router = APIRouter()

READY_STATUSES = ("diagnosed", "done")


def _take(session_id: str, take_id: str) -> dict:
    take = store.get(session_id).takes.get(take_id)
    if take is None:
        raise AppError(404, "take_not_found", "We couldn't find that take.")
    return take


def _with_plan(session_id: str, feedback: dict) -> dict:
    return {**feedback, "plan": store.get(session_id).plans.get(feedback["plan_id"])}


def _latest_feedback(session_id: str, take_id: str) -> dict | None:
    records = [f for f in store.get(session_id).feedback.values() if f["take_id"] == take_id]
    return max(records, key=lambda f: int(f["id"][2:]), default=None)


@router.get("/sessions/{session_id}/takes/{take_id}/feedback")
def get_feedback(session_id: str, take_id: str) -> dict:
    take = _take(session_id, take_id)
    feedback = _latest_feedback(session_id, take_id) if take["status"] == "done" else None
    if feedback is None:
        raise AppError(409, "wrong_state", "Feedback not ready.")
    return _with_plan(session_id, feedback)


@router.post("/sessions/{session_id}/takes/{take_id}/feedback")
def rerun_feedback(session_id: str, take_id: str) -> dict:
    take = _take(session_id, take_id)
    if take["status"] not in READY_STATUSES or take["form_status"] == "processing":
        raise AppError(409, "wrong_state", "Feedback can't run until the take has been checked.")
    feedback_id = run_feedback(session_id, take_id, wait=False)
    feedback = store.get(session_id).feedback.get(feedback_id)
    if feedback is None:
        log.error("Feedback run for take %s/%s saved nothing", session_id, take_id)
        raise storage_error()
    return _with_plan(session_id, feedback)
