"""Synthesizes a take from a score's notes: harmonic tones with a short attack and a decay, written as a mono wav."""
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
ATTACK_S = 0.015
RELEASE_S = 0.03
DECAY_PER_S = 1.2  # level falls by this factor's exponent per second, so the note fades like a plucked or bowed string
GAP_S = 0.08  # silence before the next beat, so repeated pitches are heard as separate notes
HARMONIC_WEIGHTS = (1.0, 0.5, 0.25, 0.12)
PEAK = 0.6
TAIL_S = 0.5


def midi_to_hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(midi: float, seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    wave_ = sum(w * np.sin(2 * np.pi * midi_to_hz(midi) * (k + 1) * t) for k, w in enumerate(HARMONIC_WEIGHTS))
    envelope = np.minimum(t / ATTACK_S, 1.0) * np.exp(-DECAY_PER_S * t)
    envelope *= np.clip((seconds - t) / RELEASE_S, 0.0, 1.0)
    return wave_ * envelope


def synthesize(notes: list[dict], sec_per_beat: float, downbeat_s: float) -> np.ndarray:
    """Audio for notes given as {midi, onset_beats, dur_beats}; the first beat (beat 0) sounds at downbeat_s."""
    end_s = max((n["onset_beats"] + n["dur_beats"]) * sec_per_beat for n in notes)
    audio = np.zeros(int((downbeat_s + end_s + TAIL_S) * SAMPLE_RATE))
    for note in notes:
        start = int((downbeat_s + note["onset_beats"] * sec_per_beat) * SAMPLE_RATE)
        samples = tone(note["midi"], max(note["dur_beats"] * sec_per_beat - GAP_S, 0.1))
        audio[start:start + len(samples)] += samples[: len(audio) - start]
    return audio / np.max(np.abs(audio)) * PEAK


def write_wav(path: Path, audio: np.ndarray) -> Path:
    pcm = (audio * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())
    return path
