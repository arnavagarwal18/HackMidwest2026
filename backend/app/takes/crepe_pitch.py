"""CREPE transcription: the same notes as the pYIN transcriber, from CREPE's per-frame pitch.

CREPE (TensorFlow, imported only when first used) replaces pYIN's pitch step; loading, onset detection, note splitting and
note building are transcribe.py's own, so the two transcribers differ in nothing else.
"""
import logging
import os

import librosa
import numpy as np

from .transcribe import (
    FRAME_LENGTH, GATE_MARGIN_DB, HOP_LENGTH, INSTRUMENT_RANGES_HZ, MIN_VOICED_FRAMES, SAMPLE_RATE,
    NoNotesHeard, PlayedNote, UnknownInstrument, _build_note, _load_audio, _split_into_segments,
)

logger = logging.getLogger(__name__)

CREPE_CAPACITY_ENV = "CREPE_MODEL_CAPACITY"
DEFAULT_CAPACITY = "medium"  # 3.3 s per 30 s of audio and as accurate as full (9.8 s): see scripts/crepe_vs_pyin_results.md
CAPACITIES = ("tiny", "small", "medium", "large", "full")
VOICED_CONFIDENCE = 0.5  # CREPE's own default cut-off for "a pitch is present"
STEP_MS = HOP_LENGTH * 1000 // SAMPLE_RATE


class CrepeUnavailable(Exception):
    """CREPE (the `crepe` package and TensorFlow) is not installed or could not run."""


def model_capacity() -> str:
    """The CREPE model size from CREPE_MODEL_CAPACITY; an unknown value is logged and the default is used."""
    capacity = os.environ.get(CREPE_CAPACITY_ENV, DEFAULT_CAPACITY)
    if capacity not in CAPACITIES:
        logger.error("%s=%r is not one of %s; using %r", CREPE_CAPACITY_ENV, capacity, CAPACITIES, DEFAULT_CAPACITY)
        return DEFAULT_CAPACITY
    return capacity


def _predict(audio: np.ndarray, capacity: str):
    try:
        import crepe  # lazy: TensorFlow is slow to import and not needed for the pYIN transcriber
    except ImportError as error:
        raise CrepeUnavailable("CREPE is not installed; install it with `pip install crepe tensorflow`.") from error
    _, frequency, confidence, _ = crepe.predict(
        audio, SAMPLE_RATE, model_capacity=capacity, viterbi=True, step_size=STEP_MS, verbose=0
    )
    return frequency, confidence


def frame_pitches_crepe(audio: np.ndarray, instrument: str, settings: dict, capacity: str | None = None):
    """Per 10 ms frame, as transcribe._frame_pitches: fractional MIDI (NaN if unvoiced), voiced flag, voiced probability, level in dB."""
    fmin, fmax = INSTRUMENT_RANGES_HZ[instrument]
    frequency, confidence = _predict(audio, capacity or model_capacity())
    rms = librosa.feature.rms(y=audio, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    level_db = 20 * np.log10(np.maximum(rms, 1e-10))
    loud_enough = level_db >= settings["noise_floor_db"] + GATE_MARGIN_DB

    frame_count = min(len(frequency), len(loud_enough))
    frequency, confidence, loud_enough, level_db = (
        array[:frame_count] for array in (frequency, confidence, loud_enough, level_db)
    )
    voiced = (confidence >= VOICED_CONFIDENCE) & loud_enough & (frequency >= fmin) & (frequency <= fmax)
    with np.errstate(invalid="ignore", divide="ignore"):
        midi = 69 + 12 * np.log2(frequency / 440.0) - settings["pitch_offset_cents"] / 100.0
    return np.where(voiced, midi, np.nan), voiced, confidence, level_db


def transcribe_crepe(wav_path, instrument: str, profile: dict, calib_end_s: float = 0.0) -> list[PlayedNote]:
    """transcribe.transcribe with CREPE for the pitch step; `profile` must already hold both defaults (see transcriber.py)."""
    if instrument not in INSTRUMENT_RANGES_HZ:
        raise UnknownInstrument(f"Unknown instrument {instrument!r}; use one of {sorted(INSTRUMENT_RANGES_HZ)}.")
    audio = _load_audio(wav_path, calib_end_s)
    if len(audio) < FRAME_LENGTH:
        raise NoNotesHeard("The recording has no sound after the calibration part.")

    midi, voiced, probs, level_db = frame_pitches_crepe(audio, instrument, profile)
    onset_frames = librosa.onset.onset_detect(
        y=audio, sr=SAMPLE_RATE, hop_length=HOP_LENGTH, backtrack=True, units="frames"
    )
    segments = _split_into_segments(midi, voiced, level_db, set(onset_frames.tolist()))
    notes = [
        _build_note(frames, midi, probs, level_db, calib_end_s)
        for frames in segments
        if len(frames) >= MIN_VOICED_FRAMES
    ]
    if not notes:
        raise NoNotesHeard("No notes were heard in the recording.")
    for index, note in enumerate(notes):
        note.i = index
    return notes
