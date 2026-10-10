"""pYIN transcription: audio of a one-note-at-a-time instrument in, a list of notes out."""

import logging
import warnings
from dataclasses import asdict, dataclass

import librosa
import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
HOP_LENGTH = 160  # 10 ms
FRAME_LENGTH = 1024
FRAME_S = HOP_LENGTH / SAMPLE_RATE
PITCH_RESOLUTION_SEMITONES = 0.05  # librosa default 0.1 is too coarse for cents feedback; 0.02 is numerically unstable

INSTRUMENT_RANGES_HZ = {"violin": (180.0, 2700.0), "trumpet": (150.0, 1100.0)}
DEFAULT_PROFILE = {"pitch_offset_cents": 0.0, "noise_floor_db": -60.0}

GATE_MARGIN_DB = 6.0
SMOOTHING_FRAMES = 5  # 50 ms running median
SPLIT_SEMITONES = 0.7
SPLIT_MIN_FRAMES = 4  # 40 ms
END_SILENCE_FRAMES = 8  # 80 ms
MIN_VOICED_FRAMES = 6  # 60 ms
ONSET_DIP_DB = 3.0  # an onset inside a note only counts if the level dipped this much just before it
ONSET_LOOKBACK_FRAMES = 10
EDGE_LEVEL_DB = 3.0


class TranscribeError(Exception):
    """Base for transcription failures; `code` is the stable error code for callers."""

    code = "transcribe_failed"


class NoNotesHeard(TranscribeError):
    code = "no_notes_heard"


class UnknownInstrument(TranscribeError):
    code = "unknown_instrument"


class AudioUnreadable(TranscribeError):
    code = "audio_unreadable"


@dataclass
class PlayedNote:
    i: int
    onset_s: float
    offset_s: float
    midi_float: float
    midi: int
    cents_off: float
    confidence: float
    voiced_ratio: float

    def to_dict(self) -> dict:
        return asdict(self)


def transcribe(wav_path, instrument: str, profile: dict | None = None, calib_end_s: float = 0.0) -> list[PlayedNote]:
    """Transcribe a recording into notes; times are raw recording times (calib_end_s included)."""
    if instrument not in INSTRUMENT_RANGES_HZ:
        raise UnknownInstrument(f"Unknown instrument {instrument!r}; use one of {sorted(INSTRUMENT_RANGES_HZ)}.")
    settings = {**DEFAULT_PROFILE, **(profile or {})}
    audio = _load_audio(wav_path, calib_end_s)
    if len(audio) < FRAME_LENGTH:
        raise NoNotesHeard("The recording has no sound after the calibration part.")

    midi, voiced, probs, level_db = _frame_pitches(audio, instrument, settings)
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


def _load_audio(wav_path, calib_end_s: float) -> np.ndarray:
    try:
        audio, _ = librosa.load(str(wav_path), sr=SAMPLE_RATE, mono=True, offset=max(calib_end_s, 0.0))
    except Exception as error:
        logger.exception("Could not read audio file %s", wav_path)
        raise AudioUnreadable(f"Could not read the audio file {wav_path}: {error}") from error
    return audio


def _frame_pitches(audio: np.ndarray, instrument: str, settings: dict):
    """Per 10 ms frame: pitch as fractional MIDI (NaN if unvoiced/silent), voiced flag, voiced probability, level in dB."""
    fmin, fmax = INSTRUMENT_RANGES_HZ[instrument]
    f0, voiced_flag, voiced_probs = librosa.pyin(
        audio, fmin=fmin, fmax=fmax, sr=SAMPLE_RATE, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH,
        resolution=PITCH_RESOLUTION_SEMITONES,
    )
    rms = librosa.feature.rms(y=audio, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH)[0]
    level_db = 20 * np.log10(np.maximum(rms, 1e-10))
    loud_enough = level_db >= settings["noise_floor_db"] + GATE_MARGIN_DB

    frame_count = min(len(f0), len(loud_enough))
    f0, voiced_flag, voiced_probs, loud_enough, level_db = (
        array[:frame_count] for array in (f0, voiced_flag, voiced_probs, loud_enough, level_db)
    )
    voiced = voiced_flag & loud_enough & np.isfinite(f0)
    with np.errstate(invalid="ignore", divide="ignore"):
        midi = 69 + 12 * np.log2(f0 / 440.0) - settings["pitch_offset_cents"] / 100.0
    midi = np.where(voiced, midi, np.nan)
    return midi, voiced, np.nan_to_num(voiced_probs), level_db


def _running_median(midi: np.ndarray) -> np.ndarray:
    """Centered running median over SMOOTHING_FRAMES, ignoring unvoiced (NaN) frames."""
    half = SMOOTHING_FRAMES // 2
    smoothed = np.full_like(midi, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # all-NaN windows are expected
        for i in range(len(midi)):
            smoothed[i] = np.nanmedian(midi[max(0, i - half): i + half + 1])
    return smoothed


def _onset_follows_dip(level_db: np.ndarray, frame: int) -> bool:
    """True if the level at `frame` is clearly below the level just before it (a real re-articulation)."""
    recent = level_db[max(0, frame - ONSET_LOOKBACK_FRAMES): frame + 1]
    return recent.max() - level_db[frame] >= ONSET_DIP_DB


def _split_into_segments(
    midi: np.ndarray, voiced: np.ndarray, level_db: np.ndarray, onset_frames: set[int]
) -> list[list[int]]:
    """Group voiced frame indices into notes using onsets, pitch jumps and silence."""
    smoothed = _running_median(midi)
    segments: list[list[int]] = []
    current: list[int] = []
    jump_run: list[int] = []  # consecutive voiced frames far from the current note's median
    silent_frames = 0
    split_pending = False

    def close_current(keep_jump_run: bool = True):
        nonlocal current, jump_run
        if keep_jump_run:
            current += jump_run
        if current:
            segments.append(current)
        current, jump_run = [], []

    for i in range(len(midi)):
        split_pending = split_pending or (i in onset_frames and _onset_follows_dip(level_db, i))
        if not voiced[i]:
            silent_frames += 1
            if silent_frames >= END_SILENCE_FRAMES:
                close_current()
            continue
        silent_frames = 0
        if split_pending:
            close_current()
            split_pending = False
        if current:
            if abs(smoothed[i] - np.median(midi[current])) >= SPLIT_SEMITONES:
                jump_run.append(i)
                if len(jump_run) >= SPLIT_MIN_FRAMES:
                    new_note = jump_run
                    close_current(keep_jump_run=False)
                    current = new_note
                continue
            current += jump_run
            jump_run = []
        current.append(i)
    close_current()
    return segments


def _build_note(
    frames: list[int], midi: np.ndarray, probs: np.ndarray, level_db: np.ndarray, calib_end_s: float
) -> PlayedNote:
    first, last = frames[0], frames[-1]
    # Frames are 64 ms windows, so edge frames are voiced while the window is only partly filled.
    # A frame within 3 dB of the note's median level is centred on (about) the true edge.
    sounding = [f for f in frames if level_db[f] >= np.median(level_db[frames]) - EDGE_LEVEL_DB]
    onset_frame, offset_frame = sounding[0], sounding[-1]
    voiced_ratio = len(frames) / (last - first + 1)
    midi_float = float(np.median(midi[frames]))
    rounded = int(round(midi_float))
    return PlayedNote(
        i=0,
        onset_s=calib_end_s + onset_frame * FRAME_S,
        offset_s=calib_end_s + offset_frame * FRAME_S,
        midi_float=midi_float,
        midi=rounded,
        cents_off=(midi_float - rounded) * 100.0,
        confidence=float(np.mean(probs[frames]) * voiced_ratio),
        voiced_ratio=float(voiced_ratio),
    )
