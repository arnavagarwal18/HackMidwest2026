"""Take records inside session.takes, changed under one lock so ids and updates don't race."""
import threading
from typing import Any, Callable

from .. import store
from ..errors import AppError

_takes_lock = threading.Lock()


def add_take(session_id: str, make_fields: Callable[[str], dict], before_store: Callable[[dict], None]) -> dict:
    """Create take 't<n>' (in order) from make_fields(take_id); before_store(take) runs first, e.g. to move its file."""
    with _takes_lock:
        takes = store.get(session_id).takes
        take_id = f"t{len(takes) + 1}"
        take = {"take_id": take_id, **make_fields(take_id)}
        before_store(take)
        store.update(session_id, "takes", {**takes, take_id: take})
    return take


def update_take(session_id: str, take_id: str, **changes: Any) -> None:
    with _takes_lock:
        takes = store.get(session_id).takes
        store.update(session_id, "takes", {**takes, take_id: {**takes[take_id], **changes}})


def get_take(session_id: str, take_id: str) -> dict:
    """The stored take; raises 404 session_not_found or take_not_found."""
    take = store.get(session_id).takes.get(take_id)
    if take is None:
        raise AppError(404, "take_not_found", "We couldn't find that take.")
    return take
