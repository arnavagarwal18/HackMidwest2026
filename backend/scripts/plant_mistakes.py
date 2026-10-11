"""Plant known mistakes in the clean Ode to Joy reference take, and write the answer key.

Usage (from the repo root):
    backend/.venv/Scripts/python backend/scripts/plant_mistakes.py [--video PATH] [--score PATH] [--out-dir DIR] [--key PATH]

Reads the clean recording (testdata/ode_to_joy/ode_to_joy_trumpet11.mp4) and its Trumpet in Bb score (testdata/ode_to_joy/score.musicxml),
places every note in time from the score at the score's tempo (the first note is matched to the first sound in the recording and each
note's start is snapped to the nearest sound onset), and changes the audio in three places that sit at least 2 bars apart:
  1. wrong note: one note of bar 3 pitch-shifted by 2 semitones
  2. missed note: one note of bar 6 silenced
  3. rushing: bars 9-10 time-compressed by 15% (the video of those bars is sped up by the same amount)
The doctored take goes to testdata/planted/ode_to_joy_planted.mp4 (git-ignored); the answer key, with the bars and the times, to
testdata/planted/answer_key.json. The editing and encoding helpers are the ones testdata/tools/make_mistake_takes.py uses.
"""
import argparse
import json
import logging
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))  # for app.*
sys.path.insert(0, str(REPO / "testdata" / "tools"))  # for make_mistake_takes

from app.score.exceptions import BadScoreFile  # noqa: E402
from app.score.model import Score  # noqa: E402
from app.score.parse import parse_score_file  # noqa: E402
import make_mistake_takes as edits  # noqa: E402

logger = logging.getLogger("plant_mistakes")

DEFAULT_VIDEO = REPO / "testdata" / "ode_to_joy" / "ode_to_joy_trumpet11.mp4"
DEFAULT_SCORE = REPO / "testdata" / "ode_to_joy" / "score.musicxml"
DEFAULT_OUT_DIR = REPO / "testdata" / "planted"
KEY_FILENAME = "answer_key.json"
TAKE_FILENAME = "ode_to_joy_planted.mp4"
WRONG_NOTE_BAR, MISSED_NOTE_BAR, RUSH_BARS = 3, 6, (9, 10)
WRONG_NOTE_SEMITONES = 2
MIN_BAR_GAP = 2
SNAP_TOLERANCE_S = 0.2  # how far a played onset may sit from the score's grid and still count as that note
QUIET_BLOCK_S = 0.005
VALLEY_BEFORE_S, VALLEY_AFTER_S = 0.03, 0.06  # where to look for the quiet point between notes, around a detected onset
GRID_MATCH_S = 0.12  # a note counts as lined up when an onset is this close to its grid time
CANDIDATE_STARTS = 6  # how many of the first onsets are tried as the first note


class PlantError(Exception):
    """The mistakes couldn't be planted; the message says what to change."""


@dataclass(frozen=True)
class Sounding:
    """One sounded note: same-pitch neighbours in the score are played as one long note, so they are one here."""
    bar: int
    beat_in_bar: float
    pitch_midi: int
    start_beat: float
    end_beat: float
    last_bar: int
    onset_s: float = 0.0


def sounding_notes(score: Score) -> list[Sounding]:
    notes = []
    for bar in score.bars:
        for note in bar.notes:
            if note.pitch_midi is None:
                continue
            if notes and notes[-1].pitch_midi == note.pitch_midi and abs(notes[-1].end_beat - note.start_beat) < 1e-6:
                notes[-1] = Sounding(notes[-1].bar, notes[-1].beat_in_bar, note.pitch_midi, notes[-1].start_beat, note.start_beat + note.dur_beats, bar.bar)
                continue
            notes.append(Sounding(bar.bar, note.start_beat - bar.start_beat + 1, note.pitch_midi, note.start_beat, note.start_beat + note.dur_beats, bar.bar))
    return notes


def quiet_points(audio: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """Times and levels of the signal, one value per QUIET_BLOCK_S block."""
    block = round(QUIET_BLOCK_S * rate)
    blocks = np.abs(audio).max(axis=0)[: audio.shape[1] // block * block].reshape(-1, block).max(axis=1)
    return (np.arange(len(blocks)) + 0.5) * QUIET_BLOCK_S, blocks


def quietest_near(quiet: tuple[np.ndarray, np.ndarray], onset_s: float) -> float:
    """The quietest moment around a detected onset: where one note ends and the next starts (the detector puts onsets a little early)."""
    times, levels = quiet
    near = (times >= onset_s - VALLEY_BEFORE_S) & (times <= onset_s + VALLEY_AFTER_S)
    return round(float(times[near][np.argmin(levels[near])]), 3)


def best_grid_start(notes: list[Sounding], detected: np.ndarray, seconds_per_beat: float) -> float:
    """The time of beat 0: the early onset that lines up the most notes of the score with a detected onset (the take may start with noise)."""
    def matches(grid_start: float) -> int:
        grid = np.array([grid_start + note.start_beat * seconds_per_beat for note in notes])
        return int(sum(np.abs(detected - time).min() <= GRID_MATCH_S for time in grid))
    candidates = [onset - notes[0].start_beat * seconds_per_beat for onset in detected[:CANDIDATE_STARTS]]
    if not candidates:
        raise PlantError("No sound found in the recording.")
    return max(candidates, key=lambda candidate: (matches(candidate), -candidate))


def place_in_time(notes: list[Sounding], audio: np.ndarray, rate: int, bpm: float) -> list[Sounding]:
    """Give each note its played onset: the score's grid (matched to the take), snapped to the nearest detected onset."""
    detected = librosa.onset.onset_detect(y=audio.mean(axis=0), sr=rate, units="time", backtrack=True)
    seconds_per_beat = 60.0 / bpm
    grid_start = best_grid_start(notes, detected, seconds_per_beat)
    quiet = quiet_points(audio, rate)
    placed = []
    for note in notes:
        expected = grid_start + note.start_beat * seconds_per_beat
        nearest = min(detected, key=lambda onset: abs(onset - expected))
        if abs(nearest - expected) > SNAP_TOLERANCE_S:
            raise PlantError(f"No sound onset within {SNAP_TOLERANCE_S} s of bar {note.bar} beat {note.beat_in_bar:g} (expected {expected:.2f} s). "
                             "The take doesn't follow the score at this tempo; pass --bpm.")
        placed.append(Sounding(note.bar, note.beat_in_bar, note.pitch_midi, note.start_beat, note.end_beat, note.last_bar, quietest_near(quiet, float(nearest))))
    return placed


def pick_note(notes: list[Sounding], bar: int, semitones: int) -> tuple[int, int]:
    """(index, shift) of the first note wholly inside `bar` that a shift of `semitones` (up, else down) turns into a pitch both neighbours lack,
    so it sounds as its own wrong note. A shift of 0 (a note to silence) only needs the note's neighbours to differ from each other."""
    shifts = (semitones, -semitones) if semitones else (0,)
    for index, note in enumerate(notes):
        if note.bar != bar or note.last_bar != bar or index + 1 >= len(notes):
            continue
        neighbours = {notes[i].pitch_midi for i in (index - 1, index + 1) if 0 <= i < len(notes)}
        for shift in shifts:
            if note.pitch_midi not in neighbours and note.pitch_midi + shift not in neighbours:
                return index, shift
    raise PlantError(f"No note in bar {bar} can be changed by {semitones} semitones without matching a neighbour; pick another bar.")


def note_edit(notes: list[Sounding], index: int, semitones: int = 0) -> edits.NoteEdit:
    """The note from the quiet point before it to the quiet point before the next note (the edit helpers pad their start by NOTE_MARGIN_S)."""
    note, following = notes[index], notes[index + 1]
    return edits.NoteEdit(note.bar, note.beat_in_bar, str(note.pitch_midi), note.onset_s + edits.NOTE_MARGIN_S, following.onset_s, semitones, tail_s=0.0)


def rush_phrase(notes: list[Sounding], bars: tuple[int, int]) -> edits.Phrase:
    first = next((n for n in notes if n.bar == bars[0]), None)
    after = next((n for n in notes if n.bar > bars[1]), None)
    if first is None or after is None:
        raise PlantError(f"Bars {bars[0]}-{bars[1]} and the bar after them must have notes; the score is too short.")
    return edits.Phrase(bars, first.onset_s, after.onset_s)


def check_bar_gaps(spans: list[tuple[int, int]]) -> None:
    """Each mistake's (first bar, last bar); the bars between one mistake's last bar and the next's first must be MIN_BAR_GAP apart."""
    ordered = sorted(spans)
    if any(later[0] - earlier[1] < MIN_BAR_GAP for earlier, later in zip(ordered, ordered[1:])):
        raise PlantError(f"Mistakes must be at least {MIN_BAR_GAP} bars apart; they are at bars {ordered}.")


def answer_key(args: argparse.Namespace, score: Score, wrong: edits.NoteEdit, missed: edits.NoteEdit, phrase: edits.Phrase, saved_s: float) -> dict:
    return {
        "source_video": str(args.video.relative_to(REPO)), "score": str(args.score.relative_to(REPO)), "planted_take": str((args.out_dir / TAKE_FILENAME).relative_to(REPO)),
        "take_form": {"kind": "video", "bar_from": 1, "bar_to": len(score.bars), "tempo_bpm": score.tempo_bpm, "count_in_beats": 0},
        "mistakes": [
            {"id": 1, "kind": "wrong_note", "bar": wrong.bar, "beat": wrong.beat, "source_time_s": [round(wrong.onset_s, 2), round(wrong.offset_s, 2)],
             "detail": f"pitch shifted {wrong.semitones:+d} semitones; the original note is score (written) MIDI {wrong.name}"},
            {"id": 2, "kind": "missed_note", "bar": missed.bar, "beat": missed.beat, "source_time_s": [round(missed.onset_s, 2), round(missed.offset_s, 2)],
             "detail": f"silenced; the original note is score (written) MIDI {missed.name}"},
            {"id": 3, "kind": "rushing", "bars": list(phrase.bars), "source_time_s": [round(phrase.start_s, 2), round(phrase.end_s, 2)],
             "detail": f"time-compressed by {round((edits.RUSH_RATE - 1) * 100)}% (audio and video); everything after it is {saved_s:.2f} s earlier in the take"},
        ],
        "pass_rule": "diagnosis flags a wrong note in the bar of mistake 1, a missed note in the bar of mistake 2, and rushing in the bars of mistake 3; "
                     "every other bar it flags is an extra",
        "expected_extras_note": f"bars after {phrase.bars[1]} play {saved_s:.2f} s early in the take, so late bars may be flagged as early",
    }


def plant(args: argparse.Namespace) -> dict:
    score = parse_score_file(args.score)
    bpm = args.bpm or score.tempo_bpm
    with tempfile.TemporaryDirectory() as tmp:
        audio, rate = edits.read_audio(args.video, Path(tmp))
        notes = place_in_time(sounding_notes(score), audio, rate, bpm)
        wrong = note_edit(notes, *pick_note(notes, WRONG_NOTE_BAR, WRONG_NOTE_SEMITONES))
        missed = note_edit(notes, pick_note(notes, MISSED_NOTE_BAR, 0)[0])
        phrase = rush_phrase(notes, RUSH_BARS)
        check_bar_gaps([(wrong.bar, wrong.bar), (missed.bar, missed.bar), RUSH_BARS])
        doctored = edits.speed_up_phrase(edits.silence_note(edits.shift_note(audio, rate, wrong), rate, missed), rate, phrase)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        edits.encode_take(args.video, doctored, rate, phrase, args.out_dir / TAKE_FILENAME, Path(tmp))
    saved_s = (phrase.end_s - phrase.start_s) * (1 - 1 / edits.RUSH_RATE)
    return answer_key(args, score, wrong, missed, phrase, saved_s)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--video", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--score", type=Path, default=DEFAULT_SCORE)
    parser.add_argument("--bpm", type=float, help="tempo the take was played at (default: the score's)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="where the doctored take goes (git-ignored)")
    parser.add_argument("--key", type=Path, default=DEFAULT_OUT_DIR / KEY_FILENAME)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    try:
        key = plant(args)
        args.key.parent.mkdir(parents=True, exist_ok=True)
        args.key.write_text(json.dumps(key, indent=2) + "\n", encoding="utf-8")
    except (PlantError, edits.MakeTakesError, BadScoreFile, OSError, soundfile.LibsndfileError) as error:
        logger.error("plant_mistakes failed: %s", error)
        return 1
    logger.info("wrote %s and %s", args.out_dir / TAKE_FILENAME, args.key)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
