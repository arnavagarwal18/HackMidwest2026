"""GET /sessions/{id}/takes/{take}/analysis: the take's status, errors and note-check results (polled by the browser)."""
from fastapi import APIRouter

from .. import store
from ..errors import STORAGE_ERROR_MESSAGE
from ..takes.take_store import get_take
from . import config
from .take_data import form_flags
from .timing import clean_tempo_key

router = APIRouter()

DIAGNOSED_STATUSES = ("diagnosed", "done")
FALLBACK_ERROR_MESSAGE = "Something went wrong with that take. Try recording it again."
ERROR_MESSAGES = {
    config.ERROR_NO_SCORE: "Confirm a score before recording.",
    config.ERROR_DIAGNOSIS_FAILED: "Note check failed on this take.",
    config.ERROR_STORAGE: STORAGE_ERROR_MESSAGE,
    "no_audio_track": "That recording has no sound. Check the microphone and record again.",
    "no_notes_heard": "We couldn't hear any notes. Play a little closer to the microphone and try again.",
    "too_long": "That recording is too long. Keep it under 3 minutes.",
    "decode_failed": "We couldn't read that recording. Try recording it again.",
    "transcription_failed": "We couldn't pick out the notes in that recording. Try recording it again.",
}


def _error(code: str | None) -> dict | None:
    if not code:
        return None
    return {"code": code, "message": ERROR_MESSAGES.get(code, FALLBACK_ERROR_MESSAGE)}


def _tempo(diagnosis: dict, session, take: dict) -> dict:
    key = clean_tempo_key(take["bar_from"], take["bar_to"])
    return {
        "played_bpm": diagnosis["played_bpm"],
        "target_bpm": diagnosis["target_bpm"],
        "clean_bpm": session.clean_tempo.get(key),
    }


def build_analysis(session_id: str, take_id: str) -> dict:
    session = store.get(session_id)
    take = get_take(session_id, take_id)
    diagnosis = take.get("diagnosis") if take["status"] in DIAGNOSED_STATUSES else None
    diagnosis = diagnosis or {}
    return {
        "status": take["status"],
        "error": _error(take.get("error")),
        "form_status": take.get("form_status", "none"),
        "calibrated": take.get("calibrated", False),
        "transposition": diagnosis.get("transposition") or session.transposition,
        "alignment_quality": diagnosis.get("alignment_quality"),
        "cant_tell": diagnosis.get("cant_tell", False),
        "cant_tell_reason": diagnosis.get("cant_tell_reason"),
        "tempo": _tempo(diagnosis, session, take) if diagnosis else None,
        "notes": diagnosis.get("notes", []),
        "extras": diagnosis.get("extras", []),
        "bars": diagnosis.get("bars", []),
        "problems": diagnosis.get("problems", []),
        "tier1": diagnosis.get("tier1", []),
        "form": form_flags(take),
        "media_url": f"/sessions/{session_id}/takes/{take_id}/media",
    }


@router.get("/sessions/{session_id}/takes/{take_id}/analysis")
def get_analysis(session_id: str, take_id: str) -> dict:
    return build_analysis(session_id, take_id)
