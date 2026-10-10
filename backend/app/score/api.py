"""Public Python interface of the score package."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.score.exceptions import NotConfirmed
from app.score.model import Score

CONFIRMED = "confirmed"


class SessionLike(Protocol):
    score_status: str


class ScoreStore(Protocol):
    """What get_score needs from the session store (the app.store module)."""

    def get(self, session_id: str) -> SessionLike: ...

    def session_dir(self, session_id: str) -> Path: ...


def _default_store() -> ScoreStore:
    from app import store  # imported lazily so the score package imports without the web stack

    return store


def get_score(session_id: str, store: ScoreStore | None = None) -> Score:
    """Return the session's confirmed score; raises NotConfirmed otherwise."""
    store = store or _default_store()
    status = store.get(session_id).score_status
    if status != CONFIRMED:
        raise NotConfirmed(f"The score for session {session_id} is '{status}', not confirmed yet.")
    return Score.load(store.session_dir(session_id))


def bar_at_beat(score: Score, beat: float) -> int:
    """1-based number of the bar containing `beat`; beats outside the score map to the first or last bar."""
    found = score.bars[0].bar
    for bar in score.bars:
        if bar.start_beat > beat:
            break
        found = bar.bar
    return found


def beats_to_seconds(beats: float, tempo_bpm: float) -> float:
    if tempo_bpm <= 0:
        raise ValueError(f"tempo_bpm must be positive, got {tempo_bpm}")
    return beats * 60.0 / tempo_bpm
