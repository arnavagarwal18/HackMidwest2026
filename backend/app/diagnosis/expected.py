"""Step 1: expected notes for a take's bar range, taken from a score.json dict."""
from dataclasses import dataclass

from .errors import input_error

SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass
class ExpectedNote:
    id: str
    bar: int
    idx: int
    name: str
    midi: int  # sounding pitch
    onset_beats: float  # from the start of the take's first bar
    dur_beats: float


def midi_to_name(midi: int) -> str:
    return f"{SHARP_NAMES[midi % 12]}{midi // 12 - 1}"


def _bars_in_range(score: dict, bar_from: int, bar_to: int) -> list[dict]:
    if bar_from > bar_to:
        raise input_error(f"Bar range is backwards: bar_from {bar_from} is after bar_to {bar_to}.")
    by_number = {bar["bar"]: bar for bar in score.get("bars", [])}
    missing = [n for n in range(bar_from, bar_to + 1) if n not in by_number]
    if missing:
        raise input_error(f"The score has no bar(s) {missing} (asked for bars {bar_from}-{bar_to}).")
    return [by_number[n] for n in range(bar_from, bar_to + 1)]


def _sounding_name(note: dict, transposition_semitones: int) -> str:
    if transposition_semitones == 0:
        return note["name"]
    return midi_to_name(note["pitch_midi"] + transposition_semitones)


def build_expected_notes(
    score: dict, take_id: str, bar_from: int, bar_to: int, transposition_semitones: int
) -> list[ExpectedNote]:
    """Walk bars in order, skip rests, merge tied notes, shift to sounding pitch."""
    bars = _bars_in_range(score, bar_from, bar_to)
    range_start = bars[0]["start_beat"]
    expected: list[ExpectedNote] = []
    previous: ExpectedNote | None = None
    for bar in bars:
        for note in bar["notes"]:
            if note["pitch_midi"] is None:
                previous = None
                continue
            sounding = note["pitch_midi"] + transposition_semitones
            if note["tied_from_previous"] and previous is not None and previous.midi == sounding:
                previous.dur_beats += note["dur_beats"]
                continue
            previous = ExpectedNote(
                id=f"n:{take_id}:{bar['bar']}:{note['idx']}",
                bar=bar["bar"],
                idx=note["idx"],
                name=_sounding_name(note, transposition_semitones),
                midi=sounding,
                onset_beats=note["start_beat"] - range_start,
                dur_beats=note["dur_beats"],
            )
            expected.append(previous)
    return expected


def bar_start_beats(score: dict, bar_from: int, bar_to: int) -> list[tuple[int, float]]:
    """(bar number, start beat from the start of bar_from) for each bar in the range."""
    bars = _bars_in_range(score, bar_from, bar_to)
    return [(bar["bar"], bar["start_beat"] - bars[0]["start_beat"]) for bar in bars]
