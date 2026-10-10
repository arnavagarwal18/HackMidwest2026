"""Step 9: save a take's diagnosis in session.json (this take only) and as {take}_diagnosis.json."""
import json
import logging

from .. import store
from ..errors import storage_error
from ..takes.take_store import update_take

logger = logging.getLogger("app.diagnosis")


def diagnosis_file_name(take_id: str) -> str:
    return f"{take_id}_diagnosis.json"


def save_diagnosis(session_id: str, take_id: str, diagnosis: dict, **take_changes) -> None:
    """Write the file, then the take's `diagnosis` plus `take_changes`. Raises storage_error on a failed write."""
    path = store.session_dir(session_id) / diagnosis_file_name(take_id)
    try:
        path.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
    except OSError:
        logger.exception("Could not write %s", path)
        raise storage_error()
    update_take(session_id, take_id, diagnosis=diagnosis, **take_changes)
