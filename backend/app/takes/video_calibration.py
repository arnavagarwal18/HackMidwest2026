"""Calibration from an uploaded recording: find the 3 reference notes played at its start and measure them."""
import logging
from dataclasses import dataclass

import librosa
import numpy as np

from . import calibrate
from .reference import ReferenceNote, reference_notes
from .transcribe import (
    FRAME_LENGTH, FRAME_S, HOP_LENGTH, INSTRUMENT_RANGES_HZ, PITCH_RESOLUTION_SEMITONES, SAMPLE_RATE,
)

logger = logging.getLogger("app.takes.video_calibration")

SEARCH_WINDOW_S = 20.0  # the reference notes must start within this much of the recording
MIN_NOTE_S = 0.5  # a reference note is a steady pitch for at least this long
MAX_CENTS_FROM_ASKED = 50.0
CLIP_PADDING_S = 0.25  # context around each note so the noise level can be measured


@dataclass
class FoundNote:
    first_frame: int
    last_frame: int

    @property
    def start_s(self) -> float:
        return self.first_frame * FRAME_S

    @property
    def end_s(self) -> float:
        """The end of the audio the note's last frame covers, so nothing of the note is left for transcription."""
        return self.last_frame * FRAME_S + FRAME_LENGTH / 2 / SAMPLE_RATE


def _steady_runs(matching: np.ndarray, min_frames: int, start_frame: int) -> list[tuple[int, int]]:
    """(first, last) frame of each run of True values from start_frame on that lasts at least min_frames."""
    edges = np.diff(np.concatenate(([0], matching[start_frame:].astype(int), [0])))
    firsts, lasts = np.flatnonzero(edges == 1) + start_frame, np.flatnonzero(edges == -1) + start_frame - 1
    return [(int(a), int(b)) for a, b in zip(firsts, lasts) if b - a + 1 >= min_frames]


def find_reference_notes(audio: np.ndarray, instrument: str, notes: tuple[ReferenceNote, ...]) -> list[FoundNote] | None:
    """The 3 reference notes, in order, each a steady pitch within 50 cents of the asked one; None if any is missing."""
    fmin, fmax = INSTRUMENT_RANGES_HZ[instrument]
    f0, voiced_flag, _ = librosa.pyin(
        audio, fmin=fmin, fmax=fmax, sr=SAMPLE_RATE, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH,
        resolution=PITCH_RESOLUTION_SEMITONES,
    )
    level_db = calibrate._rms_db(audio, FRAME_LENGTH, HOP_LENGTH)
    frame_count = min(len(f0), len(level_db))
    f0, voiced_flag, level_db = f0[:frame_count], voiced_flag[:frame_count], level_db[:frame_count]
    playing = voiced_flag & np.isfinite(f0) & (level_db >= calibrate.SILENCE_GATE_DB)
    min_frames = int(np.ceil(MIN_NOTE_S / FRAME_S))

    found: list[FoundNote] = []
    next_frame = 0
    for note in notes:
        with np.errstate(invalid="ignore", divide="ignore"):
            cents = 1200 * np.log2(f0 / note.hz)
        runs = _steady_runs(playing & (np.abs(cents) <= MAX_CENTS_FROM_ASKED), min_frames, next_frame)
        if not runs:
            return None
        found.append(FoundNote(*runs[0]))
        next_frame = runs[0][1] + 1
    return found


def _clips(audio: np.ndarray, found: list[FoundNote]) -> list[np.ndarray]:
    """One clip per note: the note plus some padding, never reaching into a neighbouring note."""
    pad = int(CLIP_PADDING_S * SAMPLE_RATE)
    starts = [int(note.start_s * SAMPLE_RATE) for note in found]
    ends = [int(note.end_s * SAMPLE_RATE) for note in found]
    return [
        audio[max(starts[i] - pad, ends[i - 1] if i else 0): min(ends[i] + pad, starts[i + 1] if i + 1 < len(found) else len(audio))]
        for i in range(len(found))
    ]


def calibrate_from_audio(audio: np.ndarray, instrument: str) -> tuple[dict | None, float]:
    """(profile, calib_end_s) from the reference notes at the start of the audio; (None, 0.0) when they aren't there.

    `audio` is 16 kHz mono; only its first SEARCH_WINDOW_S seconds are searched.
    """
    notes = reference_notes(instrument)
    audio = audio[: int(SEARCH_WINDOW_S * SAMPLE_RATE)]
    found = find_reference_notes(audio, instrument, notes)
    if found is None:
        logger.info("No reference notes found in the first %.0f s of the recording", SEARCH_WINDOW_S)
        return None, 0.0
    measurements = calibrate.measure_notes(_clips(audio, found), instrument, notes)
    problems = [(m.asked, m.problem) for m in measurements if m.problem]
    if problems:
        logger.warning("Reference notes found in the recording but not usable for calibration: %s", problems)
        return None, 0.0
    return calibrate.build_live_profile(measurements, 0.0, None, source="video"), found[-1].end_s
