"""Rerun diagnosis on a session's takes (after the transposition changes), in the background, then rebuild their feedback."""
import importlib
import logging

from ..takes.pipeline import give_take_feedback
from ..takes.take_store import get_take

logger = logging.getLogger("app.diagnosis")

STATUS_DONE = "done"


def _diagnosis_run():
    """`app.diagnosis.run`, looked up when called because the full pipeline arrives in a later change."""
    package = importlib.import_module("app.diagnosis")
    return getattr(package, "run", None)


def _rebuild_feedback(session_id: str, take_id: str) -> None:
    """Replace a finished take's feedback and plan with ones built from its new diagnosis; a failure is logged, never raised."""
    try:
        if get_take(session_id, take_id)["status"] != STATUS_DONE:  # failed, or still in the take pipeline, which gives its own feedback
            return
        give_take_feedback(session_id, take_id, None)
    except Exception:
        logger.exception("Feedback rebuild after the diagnosis rerun failed for take %s/%s; the new diagnosis is kept", session_id, take_id)


def rerun_takes(session_id: str, take_ids: list[str]) -> None:
    """Run diagnosis on each take in turn, then rebuild its feedback; one take failing doesn't stop the rest. Never raises."""
    run = _diagnosis_run()
    if run is None:
        logger.warning("Skipped diagnosis rerun for session %s: app.diagnosis.run doesn't exist yet", session_id)
        return
    for take_id in take_ids:
        try:
            run(session_id, take_id)
        except Exception:
            logger.exception("Diagnosis rerun failed for take %s/%s", session_id, take_id)
            continue
        _rebuild_feedback(session_id, take_id)
