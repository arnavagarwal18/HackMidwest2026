"""Session store: in-memory dict backed by data/sessions/{session_id}/session.json."""
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .errors import AppError, storage_error

logger = logging.getLogger("app.store")

SESSIONS_ROOT = Path(__file__).resolve().parents[2] / "data" / "sessions"
SESSION_FILE = "session.json"
INSTRUMENTS = ("violin", "trumpet")
DEFAULT_PERSONA = "standard"  # the coach style of a session that never picked one


class SessionNotFound(AppError):
    def __init__(self, session_id: str):
        super().__init__(404, "session_not_found", "We couldn't find that practice session. Start a new one.")
        self.session_id = session_id


@dataclass
class Session:
    session_id: str
    instrument: str
    created_at: str
    score_status: str = "none"  # none | scanning | scanned | failed | confirmed
    score_error: str | None = None
    doubtful_bars: list = field(default_factory=list)
    double_checked: bool = False
    referee: dict | None = None  # the referee's report for the last photo scan; None if it never ran (old sessions)
    calibration: dict | None = None
    transposition: dict | None = None  # {semitones, source}; set by the first diagnosed take
    takes: dict[str, dict] = field(default_factory=dict)
    feedback: dict[str, dict] = field(default_factory=dict)
    plans: dict[str, dict] = field(default_factory=dict)
    progress: dict = field(default_factory=dict)
    clean_tempo: dict[str, float] = field(default_factory=dict)  # '{bar_from}-{bar_to}' -> BPM
    persona: str = DEFAULT_PERSONA  # the coach style the learner picked; session files from before personas load as 'standard'


_READ_ONLY_FIELDS = ("session_id", "created_at")
_UPDATABLE_FIELDS = {f.name for f in fields(Session)} - set(_READ_ONLY_FIELDS)
_sessions: dict[str, Session] = {}
_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(session_id: str) -> threading.Lock:
    with _registry_lock:
        return _locks.setdefault(session_id, threading.Lock())


def session_dir(session_id: str) -> Path:
    return SESSIONS_ROOT / session_id


def _save(session: Session) -> None:
    folder = session_dir(session.session_id)
    target = folder / SESSION_FILE
    temp = folder / (SESSION_FILE + ".tmp")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")
        os.replace(temp, target)
    except OSError:
        logger.exception("Could not write session file at %s", target)
        raise storage_error()


def _load(session_id: str) -> Session | None:
    path = session_dir(session_id) / SESSION_FILE
    if not path.is_file():
        return None
    try:
        return Session(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        logger.exception("Could not read session file at %s", path)
        raise storage_error()


def create(instrument: str, persona: str = DEFAULT_PERSONA) -> Session:
    if instrument not in INSTRUMENTS:
        raise AppError(422, "bad_request", "Pick violin or trumpet.")
    session = Session(
        session_id=uuid.uuid4().hex,
        instrument=instrument,
        created_at=datetime.now(timezone.utc).isoformat(),
        persona=persona,
    )
    with _lock_for(session.session_id):
        _save(session)
        _sessions[session.session_id] = session
    return session


def get(session_id: str) -> Session:
    session = _sessions.get(session_id)
    if session is None and session_id.isalnum():  # alnum guard keeps ids from escaping the folder
        with _lock_for(session_id):
            session = _sessions.get(session_id) or _load(session_id)
            if session is not None:
                _sessions[session_id] = session
    if session is None:
        raise SessionNotFound(session_id)
    return session


def modify(session_id: str, key: str, change: Callable[[Any], Any]) -> Session:
    """Read-modify-write one session field under the per-session lock: set it to change(current value), then save.

    `change` runs while the lock is held, so it must not call back into the store.
    """
    if key not in _UPDATABLE_FIELDS:
        raise ValueError(f"Session field '{key}' can't be updated")
    session = get(session_id)
    with _lock_for(session_id):
        previous = getattr(session, key)
        setattr(session, key, change(previous))
        try:
            _save(session)
        except AppError:
            setattr(session, key, previous)
            raise
    return session


def update(session_id: str, key: str, value: Any) -> Session:
    """Set one session field under the per-session lock and save to disk."""
    return modify(session_id, key, lambda _: value)
