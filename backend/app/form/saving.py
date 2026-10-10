"""Saving a take's form result: {take}_form.json, and take.form with the take's form_status."""
import json
import logging
import os
from pathlib import Path

from .. import store
from ..errors import storage_error
from ..takes.take_store import update_take
from . import config

logger = logging.getLogger("app.form")


def form_path(session_id: str, take_id: str) -> Path:
    return store.session_dir(session_id) / f"{take_id}{config.FORM_FILE_SUFFIX}"


def save_form(session_id: str, take_id: str, form: dict, form_status: str) -> None:
    """Write the file (atomically), then take.form and take.form_status. Raises storage_error if the file can't be written."""
    target = form_path(session_id, take_id)
    temp = target.with_name(target.name + ".tmp")
    try:
        temp.write_text(json.dumps(form, indent=2), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        logger.exception("Could not write form file at %s", target)
        temp.unlink(missing_ok=True)
        raise storage_error()
    update_take(session_id, take_id, form=form, form_status=form_status)
