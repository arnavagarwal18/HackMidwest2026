"""Reading a take's saved diagnosis: its form flags, `get` and `lookup`."""
import logging

from .. import store
from ..agents.context import index_items
from ..takes.take_store import get_take

logger = logging.getLogger("app.diagnosis")

ID_PARTS = 3  # at least '{prefix}:{take}:{rest}'
TAKE_ID_PART = 1


def form_flags(take: dict) -> list[dict]:
    """The form flags LLD-4 saved on the take (take.form.flags); none until it finishes."""
    return (take.get("form") or {}).get("flags") or []


def get(session_id: str, take_id: str) -> dict:
    """The take's saved diagnosis ({} until diagnosed). Raises 404 for an unknown session or take."""
    return get_take(session_id, take_id).get("diagnosis") or {}


def lookup(session_id: str, measurement_id: str) -> dict | None:
    """The NoteResult, Extra, BarResult, Problem or FormFlag with this ID, or None. Never raises."""
    try:
        parts = measurement_id.split(":")
        if len(parts) < ID_PARTS:
            return None
        take = store.get(session_id).takes.get(parts[TAKE_ID_PART])
        if take is None or not take.get("diagnosis"):
            return None
        return index_items(take["diagnosis"], form_flags(take)).get(measurement_id)
    except Exception:
        logger.exception("Could not look up %r in session %s", measurement_id, session_id)
        return None
