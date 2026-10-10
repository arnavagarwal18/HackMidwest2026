"""Reading a take's saved form flags."""
from typing import Any

from .. import store
from ..takes.take_store import get_take

FormFlag = dict[str, Any]  # {id 'f:{take}:{k}', rule, label, start_s, end_s, peak_s, value, threshold, unit, direction, severity, confidence, side, bars, linked}

FLAG_ID_PARTS = 3  # 'f:{take}:{k}'
TAKE_ID_PART = 1


def get_flags(session_id: str, take_id: str) -> list[FormFlag]:
    """The take's form flags ([] until the form check has run). Raises 404 for an unknown session or take."""
    return (get_take(session_id, take_id).get("form") or {}).get("flags") or []


def get_flag(session_id: str, flag_id: str) -> FormFlag | None:
    """The flag with this id, or None for an unknown flag, take or session."""
    parts = flag_id.split(":")
    if len(parts) != FLAG_ID_PARTS or parts[0] != "f":
        return None
    try:
        take = store.get(session_id).takes.get(parts[TAKE_ID_PART])
    except store.SessionNotFound:
        return None
    if take is None:
        return None
    return next((flag for flag in (take.get("form") or {}).get("flags") or [] if flag["id"] == flag_id), None)
