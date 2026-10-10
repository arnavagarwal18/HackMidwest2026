"""A session's chat turns, kept in chat.json in the session folder (the session record itself has no chat field)."""
import json
import logging
import os
from datetime import datetime, timezone

from app import store
from app.errors import storage_error

log = logging.getLogger(__name__)

CHAT_FILE = "chat.json"


def load_turns(session_id: str) -> list[dict]:
    path = store.session_dir(session_id) / CHAT_FILE
    if not path.is_file():
        return []
    try:
        turns = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.exception("Could not read the chat %s", path)
        raise storage_error()
    if not isinstance(turns, list):
        log.error("The chat %s is not a list of turns", path)
        raise storage_error()
    return turns


def append_turn(session_id: str, turn: dict) -> None:
    """Add one turn to the end of the chat. One writer per session at a time is the caller's job."""
    turns = [*load_turns(session_id), turn]
    folder = store.session_dir(session_id)
    target, temp = folder / CHAT_FILE, folder / (CHAT_FILE + ".tmp")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(turns, indent=2), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        log.exception("Could not write the chat %s", target)
        raise storage_error()


def new_turn(turns: list[dict], role: str, text: str, take_id: str | None, **extra) -> dict:
    """A chat record numbered after the saved turns; `role` is 'user' or 'instructor'."""
    return {"id": f"c{len(turns) + 1}", "role": role, "text": text, "take_id": take_id,
            "created_at": datetime.now(timezone.utc).isoformat(), **extra}
