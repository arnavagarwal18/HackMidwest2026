"""The transcriber the pipeline calls, chosen by the TRANSCRIBER setting: pyin (the default) or crepe."""
import logging
import os

from . import transcribe as pyin
from .crepe_pitch import CrepeUnavailable, transcribe_crepe
from .transcribe import DEFAULT_PROFILE, PlayedNote, TranscribeError

logger = logging.getLogger(__name__)

TRANSCRIBER_ENV = "TRANSCRIBER"
PYIN, CREPE = "pyin", "crepe"
DEFAULT_TRANSCRIBER = PYIN


def selected_transcriber() -> str:
    """The TRANSCRIBER setting; an unknown value is logged and pYIN is used."""
    name = os.environ.get(TRANSCRIBER_ENV, DEFAULT_TRANSCRIBER).strip().lower()
    if name not in (PYIN, CREPE):
        logger.error("%s=%r is not 'pyin' or 'crepe'; using pyin", TRANSCRIBER_ENV, name)
        return PYIN
    return name


def transcribe(wav_path, instrument: str, profile: dict | None = None, calib_end_s: float = 0.0) -> list[PlayedNote]:
    """Transcribe with the selected transcriber; if CREPE can't run, log why and use pYIN. Notes from the recording itself
    (no notes heard, unreadable audio, unknown instrument) are errors for either transcriber."""
    if selected_transcriber() == CREPE:
        try:
            return transcribe_crepe(wav_path, instrument, {**DEFAULT_PROFILE, **(profile or {})}, calib_end_s)
        except TranscribeError:
            raise
        except CrepeUnavailable:
            logger.exception("CREPE is not available; transcribing with pyin instead")
        except Exception:
            logger.exception("CREPE failed on %s; transcribing with pyin instead", wav_path)
    return pyin.transcribe(wav_path, instrument, profile, calib_end_s)
