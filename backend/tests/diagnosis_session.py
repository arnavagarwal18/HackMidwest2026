"""Builds a session with a confirmed score and takes holding transcribed notes, for run / rerank / route tests."""
import json

from app import diagnosis, store
from app.takes.take_store import add_take
from app.takes.validation import TakeRequest, new_take_fields
from diagnosis_samples import make_scale_score


def make_session(score: dict | None = None, confirmed: bool = True, instrument: str = "violin") -> str:
    session_id = store.create(instrument).session_id
    if score is not None:
        (store.session_dir(session_id) / "score.json").write_text(json.dumps(score), encoding="utf-8")
    if confirmed:
        store.update(session_id, "score_status", "confirmed")
    return session_id


def add_transcribed_take(session_id: str, played: list[dict], bar_to: int = 4, status: str = "transcribed") -> str:
    """Take with tempo 120 and a recorded downbeat at 1.0 s, like diagnosis_samples.make_take."""
    request = TakeRequest(
        kind="mic", source="recorded", bar_from=1, bar_to=bar_to, tempo_bpm=120, count_in_beats=4, downbeat_s=1.0
    )
    take = add_take(
        session_id,
        lambda take_id: {**new_take_fields(take_id, request, f"{take_id}.webm"), "notes": played, "status": status},
        lambda take: None,
    )
    return take["take_id"]


def diagnosed_session(played: list[dict], score: dict | None = None) -> tuple[str, str]:
    """(session_id, take_id) after diagnosis.run on a take with these notes."""
    session_id = make_session(score or make_scale_score())
    take_id = add_transcribed_take(session_id, played)
    diagnosis.run(session_id, take_id)
    return session_id, take_id
