"""Steps of the take pipeline other than audio extraction: calibration, transcription and the lazy LLD-3/LLD-4 hooks."""
import importlib
import json
import logging
from typing import Callable

import librosa

from .. import store
from .calibrate import default_profile
from .take_store import update_take
from .transcribe import SAMPLE_RATE, AudioUnreadable, NoNotesHeard
from .transcriber import transcribe
from .video_calibration import SEARCH_WINDOW_S, calibrate_from_audio

logger = logging.getLogger("app.takes.pipeline")

DEFAULT_PROFILE = default_profile()

Step = Callable[[str, str], None]


class StepFailed(Exception):
    """A pipeline step failed; `code` is what gets stored in take.error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def calibrate_from_video(session_id: str, take_id: str) -> tuple[dict | None, float]:
    """(profile, calib_end_s) from reference notes at the start of an uploaded take; (None, 0.0) when it doesn't apply.

    Skipped for recorded takes and when the session already has a live calibration. Never fails the take:
    if the audio can't be analysed the error is logged and the take is processed uncalibrated.
    """
    session = store.get(session_id)
    take = session.takes[take_id]
    if take["source"] != "uploaded" or (session.calibration or {}).get("source") == "live":
        return None, 0.0
    try:
        audio, _ = librosa.load(str(store.session_dir(session_id) / take["audio"]), sr=SAMPLE_RATE, mono=True,
                                duration=SEARCH_WINDOW_S)
        return calibrate_from_audio(audio, session.instrument)
    except Exception:
        logger.exception("Calibration from the video of take %s/%s failed; using the default profile", session_id, take_id)
        return None, 0.0


def calibration_profile(session_id: str, take: dict) -> tuple[dict, float]:
    """The profile to transcribe with and the seconds of the recording used for calibrating."""
    video_profile, calib_end_s = calibrate_from_video(session_id, take["take_id"])
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


def resolve_feedback_step() -> Step | None:
    """app.agents.run.run_feedback; raises StepFailed("feedback_unavailable") if the agents can't be imported (strands, boto3...)."""
    try:
        return resolve_step("app.agents.run", "run_feedback")
    except Exception as exc:
        logger.exception("The feedback agents could not be imported")
        raise StepFailed("feedback_unavailable") from exc
