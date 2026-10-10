"""Take records inside session.takes, changed under one lock so ids and updates don't race."""
import threading
from typing import Any, Callable

from .. import store

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
