"""GET a feedback run's trace: what each agent did, from the trace file the run saved."""
import json
import logging

from fastapi import APIRouter

from app import store
from app.errors import AppError, storage_error

log = logging.getLogger(__name__)
router = APIRouter()


def _read_events(session_id: str, feedback_id: str) -> list[dict]:
    path = store.session_dir(session_id) / f"{feedback_id}_trace.json"
    if not path.is_file():
        raise AppError(404, "trace_missing", "This feedback has no trace.")
    try:
        events = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("Could not read the trace %s", path)
        raise storage_error()
    if not isinstance(events, list):
        log.error("The trace %s is not a list of events", path)
        raise storage_error()
    return events


@router.get("/sessions/{session_id}/feedback/{feedback_id}/trace")
def get_trace(session_id: str, feedback_id: str) -> dict:
    feedback = store.get(session_id).feedback.get(feedback_id)
    if feedback is None:
        raise AppError(404, "feedback_not_found", "We couldn't find that feedback.")
    return {"feedback_id": feedback_id, "mode": feedback["mode"], "events": _read_events(session_id, feedback_id)}
