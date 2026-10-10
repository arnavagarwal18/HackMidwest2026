"""Rerun diagnosis on a session's takes (after the transposition changes), in the background."""
import importlib
import logging

logger = logging.getLogger("app.diagnosis")


def _diagnosis_run():
    """`app.diagnosis.run`, looked up when called because the full pipeline arrives in a later change."""
    package = importlib.import_module("app.diagnosis")
    return getattr(package, "run", None)


def rerun_takes(session_id: str, take_ids: list[str]) -> None:
    """Run diagnosis on each take in turn; one take failing doesn't stop the rest. Never raises."""
    run = _diagnosis_run()
    if run is None:
        logger.warning("Skipped diagnosis rerun for session %s: app.diagnosis.run doesn't exist yet", session_id)
        return
    for take_id in take_ids:
        try:
            run(session_id, take_id)
        except Exception:
            logger.exception("Diagnosis rerun failed for take %s/%s", session_id, take_id)
