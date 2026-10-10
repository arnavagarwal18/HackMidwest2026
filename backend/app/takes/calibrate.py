"""Calibration analysis: measure reference-note clips and a click clip into a calibration profile."""
import logging
from dataclasses import dataclass

import librosa
import numpy as np

from .reference import ReferenceNote
from .transcribe import (
    FRAME_LENGTH, FRAME_S, HOP_LENGTH, INSTRUMENT_RANGES_HZ, PITCH_RESOLUTION_SEMITONES, SAMPLE_RATE,
)

logger = logging.getLogger("app.takes.calibrate")

NOT_HEARD_MIN_VOICED_S = 0.5
MIDDLE_FRACTION = 0.6  # keep the middle 60% of voiced frames
OFF_PITCH_CENTS = 50.0
NOISE_FRACTION = 0.1  # the quietest 10% of frames
MIN_NOTE_ABOVE_NOISE_DB = 15.0
SILENCE_GATE_DB = -60.0  # frames quieter than this can't be a played note
REFINE_FFT_SIZE = 2 ** 18
REFINE_SEARCH_CENTS = 60.0
LATENCY_RANGE_MS = (0.0, 500.0)

DEFAULT_NOISE_FLOOR_DB = -60.0
CLICK_FRAME = 64  # 4 ms
CLICK_HOP = 16  # 1 ms
CLICK_ABOVE_BACKGROUND_DB = 12.0
CLICK_MIN_BACKGROUND_DB = -70.0

NOT_HEARD, OFF_PITCH, TOO_NOISY = "not_heard", "off_pitch", "too_noisy"


@dataclass
class NoteMeasurement:
    asked: str
    asked_hz: float
    measured_hz: float | None
    cents: float | None
    level_db: float | None
    noise_db: float
    problem: str | None

    def to_note(self) -> dict:
        """The entry stored in the profile's notes list."""
        return {
            "asked": self.asked,
            "asked_hz": round(self.asked_hz, 2),
            "measured_hz": None if self.measured_hz is None else round(self.measured_hz, 2),
            "cents": None if self.cents is None else round(self.cents, 2),
            "problem": self.problem,
        }


def default_profile() -> dict:
    return {
        "source": "default", "calibrated": False, "pitch_offset_cents": 0.0,
        "noise_floor_db": DEFAULT_NOISE_FLOOR_DB, "pickup_db": {"low": 0.0, "mid": 0.0, "high": 0.0},
        "latency_ms": 0.0, "instrument_offset_cents": None, "notes": [],
    }


def _rms_db(audio: np.ndarray, frame_length: int, hop_length: int) -> np.ndarray:
    rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length, center=False)[0]
    return 20 * np.log10(np.maximum(rms, 1e-10))


def _refine_hz(audio: np.ndarray, coarse_hz: float, first_frame: int, last_frame: int) -> float:
    """Spectral peak near the coarse pitch over the given frames: pyin's pitch grid is too coarse for cents."""
    start = max(0, first_frame * HOP_LENGTH - FRAME_LENGTH // 2)
    segment = audio[start: last_frame * HOP_LENGTH + FRAME_LENGTH // 2]
    spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment)), n=REFINE_FFT_SIZE))
    freqs = np.fft.rfftfreq(REFINE_FFT_SIZE, 1 / SAMPLE_RATE)
    window = np.flatnonzero(np.abs(1200 * np.log2(np.maximum(freqs, 1e-9) / coarse_hz)) <= REFINE_SEARCH_CENTS)
    if len(window) < 3:
        return coarse_hz
    peak = window[np.argmax(spectrum[window])]
    if peak in (window[0], window[-1]):
        return coarse_hz
    left, mid, right = np.log(np.maximum(spectrum[peak - 1: peak + 2], 1e-12))
    shift = 0.5 * (left - right) / (left - 2 * mid + right) if left - 2 * mid + right else 0.0
    return float(freqs[peak] + shift * (freqs[1] - freqs[0]))


def measure_note(audio: np.ndarray, instrument: str, note: ReferenceNote) -> NoteMeasurement:
    """Pitch (median of the middle 60% of voiced frames), level and background noise of one reference clip."""
    fmin, fmax = INSTRUMENT_RANGES_HZ[instrument]
    f0, voiced_flag, _ = librosa.pyin(
        audio, fmin=fmin, fmax=fmax, sr=SAMPLE_RATE, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH,
        resolution=PITCH_RESOLUTION_SEMITONES,
    )
    level_db = _rms_db(audio, FRAME_LENGTH, HOP_LENGTH)
    frame_count = min(len(f0), len(level_db))
    f0, voiced_flag, level_db = f0[:frame_count], voiced_flag[:frame_count], level_db[:frame_count]

    quietest = np.sort(level_db)[: max(1, int(frame_count * NOISE_FRACTION))]
    noise_db = float(np.mean(quietest)) if frame_count else SILENCE_GATE_DB
    voiced = np.flatnonzero(voiced_flag & np.isfinite(f0) & (level_db >= SILENCE_GATE_DB))
    result = NoteMeasurement(note.name, note.hz, None, None, None, noise_db, None)
    if len(voiced) < NOT_HEARD_MIN_VOICED_S / FRAME_S:
        result.problem = NOT_HEARD
        return result

    trim = int(len(voiced) * (1 - MIDDLE_FRACTION) / 2)
    middle = voiced[trim: len(voiced) - trim]
    result.measured_hz = _refine_hz(audio, float(np.median(f0[middle])), middle[0], middle[-1])
    result.cents = 1200 * float(np.log2(result.measured_hz / note.hz))
    result.level_db = float(np.median(level_db[middle]))
    if result.level_db - noise_db < MIN_NOTE_ABOVE_NOISE_DB:
        result.problem = TOO_NOISY
    elif abs(result.cents) > OFF_PITCH_CENTS:
        result.problem = OFF_PITCH
    return result


def measure_notes(clips: list[np.ndarray], instrument: str, notes: tuple[ReferenceNote, ...]) -> list[NoteMeasurement]:
    return [measure_note(audio, instrument, note) for audio, note in zip(clips, notes)]


def build_live_profile(measurements: list[NoteMeasurement], latency_ms: float, instrument_offset_cents: float | None) -> dict:
    """Profile from three problem-free reference measurements (low, mid, high)."""
    low, mid, high = (m.level_db for m in measurements)
    return {
        "source": "live", "calibrated": True,
        "pitch_offset_cents": round(float(np.mean([m.cents for m in measurements])), 2),
        "noise_floor_db": round(min(m.noise_db for m in measurements), 2),
        "pickup_db": {"low": round(low - mid, 2), "mid": 0.0, "high": round(high - mid, 2)},
        "latency_ms": round(latency_ms, 1),
        "instrument_offset_cents": None if instrument_offset_cents is None else round(instrument_offset_cents, 2),
        "notes": [m.to_note() for m in measurements],
    }


def instrument_offset_cents(measurements: list[NoteMeasurement]) -> float | None:
    """Mean cents of the instrument clips that could be measured; never fails the calibration."""
    usable = [m.cents for m in measurements if m.problem is None]
    for m in measurements:
        if m.problem is not None:
            logger.warning("Instrument clip %s ignored: %s", m.asked, m.problem)
    return float(np.mean(usable)) if usable else None


def measure_latency_ms(click_audio: np.ndarray, click_at_s: float) -> float:
    """Milliseconds from click_at_s to the first onset in the click clip, clamped to 0..500."""
    if len(click_audio) < CLICK_FRAME:
        logger.warning("Click clip is too short to find a click; using 0 ms latency")
        return 0.0
    level_db = _rms_db(click_audio, CLICK_FRAME, CLICK_HOP)
    background_db = max(float(np.median(level_db)), CLICK_MIN_BACKGROUND_DB)
    loud = np.flatnonzero(level_db > background_db + CLICK_ABOVE_BACKGROUND_DB)
    if len(loud) == 0:
        logger.warning("No click was heard in the click clip; using 0 ms latency")
        return 0.0
    onset_s = (loud[0] * CLICK_HOP + CLICK_FRAME / 2) / SAMPLE_RATE
    return float(np.clip((onset_s - click_at_s) * 1000, *LATENCY_RANGE_MS))


def problem_message(m: NoteMeasurement) -> str:
    if m.problem == NOT_HEARD:
        return f"{m.asked} wasn't heard: is your microphone on and the tone page playing {m.asked}?"
    if m.problem == TOO_NOISY:
        return f"{m.asked} was too noisy: find a quieter spot and play it again."
    return f"{m.asked} was {abs(m.cents):.0f} cents off: is the tone page playing {m.asked}?"
