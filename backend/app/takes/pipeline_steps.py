"""Steps of the take pipeline other than audio extraction: calibration, transcription and the lazy LLD-3/LLD-4 hooks."""
import importlib
import json
import logging
from typing import Callable

from .. import store
from .take_store import update_take
from .transcribe import AudioUnreadable, NoNotesHeard, transcribe

logger = logging.getLogger("app.takes.pipeline")

DEFAULT_PROFILE = {
    "source": "default", "calibrated": False, "pitch_offset_cents": 0, "noise_floor_db": -60,
    "pickup_db": {"low": 0, "mid": 0, "high": 0}, "latency_ms": 0, "instrument_offset_cents": None, "notes": [],
}

Step = Callable[[str, str], None]


class StepFailed(Exception):
    """A pipeline step failed; `code` is what gets stored in take.error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def calibrate_from_video(session_id: str, take_id: str) -> tuple[dict | None, float]:
    """Hook for calibrating from a video's opening seconds; returns (profile, calib_end_s). Not built yet."""
    return None, 0.0


def calibration_profile(session_id: str, take: dict) -> tuple[dict, float]:
    """The profile to transcribe with and the seconds of the recording used for calibrating."""
    video_profile, calib_end_s = calibrate_from_video(session_id, take["take_id"]) if take["kind"] == "video" else (None, 0.0)
    profile = video_profile or store.get(session_id).calibration or DEFAULT_PROFILE
    return profile, calib_end_s


def transcribe_take(session_id: str, take_id: str, transcriber=None) -> None:
    """Transcribe the take's audio, store the notes on the take and as {take_id}_notes.json, set status 'transcribed'."""
    transcriber = transcriber or transcribe
    session = store.get(session_id)
    take = session.takes[take_id]
    profile, calib_end_s = calibration_profile(session_id, take)
    folder = store.session_dir(session_id)
    try:
        notes = [note.to_dict() for note in transcriber(folder / take["audio"], session.instrument, profile, calib_end_s)]
        (folder / f"{take_id}_notes.json").write_text(json.dumps(notes), encoding="utf-8")
    except NoNotesHeard:
        raise StepFailed("no_notes_heard")
    except AudioUnreadable:
        logger.exception("Transcriber could not read the audio of take %s/%s", session_id, take_id)
        raise StepFailed("decode_failed")
    except Exception:
        logger.exception("Transcription of take %s/%s failed", session_id, take_id)
        raise StepFailed("transcription_failed")
    update_take(session_id, take_id, notes=notes, calibrated=bool(profile.get("calibrated")),
                calib_end_s=calib_end_s, status="transcribed")


def resolve_step(module_name: str, attr: str = "run") -> Step | None:
    """Find `attr` in another team's module at call time; None (with a warning) while it doesn't exist yet."""
    try:
        run = getattr(importlib.import_module(module_name), attr, None)
    except ModuleNotFoundError as exc:
        if exc.name != module_name:
            raise
        run = None
    if run is None:
        logger.warning("%s.%s is not available yet; skipping that step", module_name, attr)
    return run
