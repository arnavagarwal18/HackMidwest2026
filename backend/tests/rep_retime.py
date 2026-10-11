"""Cuts a clean practice rep out of a real, uneven take: each note of a bar range is moved onto its expected onset.

The real trumpet take plays bars 7-8 80-300 ms off the grid, so a rep cut straight from it fails a 50 ms pass mark. Here
every note keeps the sound it was played with but starts exactly where the diagnosis expected it (expected_onset_s).
"""
import json
from pathlib import Path

import numpy as np
import soundfile as sf

LEAD_IN_S = 0.5
TAIL_S = 0.6
FADE_S = 0.01
GAP_S = 0.07  # silence before the next note, so a repeated pitch is still heard as a new note
LAST_NOTE_MAX_S = 0.9
MS_PER_S = 1000


class RetimeError(Exception):
    """The take has no usable notes for the bars, or its files are missing."""


def _read_json(path: Path):
    if not path.is_file():
        raise RetimeError(f"{path.name} is missing from {path.parent}")
    return json.loads(path.read_text(encoding="utf-8"))


def _played_onsets(diagnosis: dict) -> list[float]:
    """Every onset the player produced (judged notes and extras), sorted, so a cut never runs into the next sound."""
    judged = [n["expected_onset_s"] + n["timing_ms"] / MS_PER_S for n in diagnosis["notes"] if n.get("timing_ms") is not None]
    return sorted(judged + [extra["onset_s"] for extra in diagnosis["extras"]])


def _next_after(onsets: list[float], onset_s: float) -> float | None:
    later = [o for o in onsets if o > onset_s + 1e-6]
    return later[0] if later else None


def _faded(clip: np.ndarray, sample_rate: int) -> np.ndarray:
    fade = min(int(FADE_S * sample_rate), len(clip))
    if fade:
        clip = clip.copy()
        clip[-fade:] *= np.linspace(1.0, 0.0, fade)
    return clip


def retimed_rep_wav(session_dir: Path, take_id: str, bar_from: int, bar_to: int, target: Path) -> Path:
    """Write a wav of the take's `ok` notes in the bars, each at its expected onset (the first after LEAD_IN_S)."""
    diagnosis = _read_json(session_dir / f"{take_id}_diagnosis.json")
    audio, sample_rate = sf.read(session_dir / f"{take_id}.wav", dtype="float32")
    notes = [n for n in diagnosis["notes"]
             if bar_from <= n["bar"] <= bar_to and n["status"] == "ok" and n.get("timing_ms") is not None]
    if not notes:
        raise RetimeError(f"take {take_id} has no ok notes in bars {bar_from}-{bar_to}")
    onsets = _played_onsets(diagnosis)
    shift_s = LEAD_IN_S - notes[0]["expected_onset_s"]
    rep = np.zeros(int((notes[-1]["expected_onset_s"] + shift_s + LAST_NOTE_MAX_S + TAIL_S) * sample_rate))
    for position, note in enumerate(notes):
        played_s = note["expected_onset_s"] + note["timing_ms"] / MS_PER_S
        slot_end = notes[position + 1]["expected_onset_s"] if position + 1 < len(notes) else note["expected_onset_s"] + LAST_NOTE_MAX_S
        played_end = _next_after(onsets, played_s)
        length_s = min(slot_end - GAP_S - note["expected_onset_s"], (played_end - played_s) if played_end else LAST_NOTE_MAX_S)
        clip = _faded(audio[int(played_s * sample_rate):int((played_s + length_s) * sample_rate)], sample_rate)
        start = int((note["expected_onset_s"] + shift_s) * sample_rate)
        rep[start:start + len(clip)] = clip[: len(rep) - start]
    sf.write(target, rep, sample_rate)
    return target
