"""Turn a flat list of note events into bars (pure Python, no music21)."""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

from app.score.model import Bar, Note

EPSILON = 1e-6
SIXTEENTH = 0.25  # in quarter-note beats
PRECISION = 4  # decimal places kept for beat values (keeps triplets stable)


@dataclass
class RawEvent:
    """One note or rest as read from the file; start/dur in quarter-note beats."""

    start: float
    dur: float
    pitch_midi: int | None
    name: str
    tied_from_previous: bool = False


def round_to_16th(beats: float) -> float:
    return round(beats / SIXTEENTH) * SIXTEENTH


def synthesize_spans(beats_per_bar: float, end_beat: float) -> list[tuple[float, float]]:
    """Equal-length (start, length) bar spans covering [0, end_beat]."""
    count = max(1, math.ceil(end_beat / beats_per_bar - EPSILON))
    return [(i * beats_per_bar, beats_per_bar) for i in range(count)]


def _place_events(events: list[RawEvent], spans: list[tuple[float, float]]) -> list[list[RawEvent]]:
    """Assign events to bars, splitting pitched notes that cross a barline."""
    starts = [start for start, _ in spans]
    placed: list[list[RawEvent]] = [[] for _ in spans]
    for event in sorted(events, key=lambda e: e.start):
        index = max(0, bisect_right(starts, event.start + EPSILON) - 1)
        cursor, remaining, tied = event.start, event.dur, event.tied_from_previous
        while remaining > EPSILON:
            is_last = index == len(spans) - 1
            bar_end = spans[index][0] + spans[index][1]
            piece = remaining if is_last else min(remaining, bar_end - cursor)
            placed[index].append(RawEvent(cursor, piece, event.pitch_midi, event.name, tied))
            cursor += piece
            remaining -= piece
            if is_last or event.pitch_midi is None:
                break
            index += 1
            tied = True
    return placed


def _fill_rests(events: list[RawEvent], start: float, length: float) -> list[RawEvent]:
    """Insert rests into the gaps of one bar (MIDI files have no explicit rests)."""
    filled: list[RawEvent] = []
    cursor = start
    for event in events:
        if event.start - cursor > EPSILON:
            filled.append(RawEvent(cursor, event.start - cursor, None, "rest"))
        filled.append(event)
        cursor = max(cursor, event.start + event.dur)
    if start + length - cursor > EPSILON:
        filled.append(RawEvent(cursor, start + length - cursor, None, "rest"))
    return filled


def build_bars(
    events: list[RawEvent], spans: list[tuple[float, float]], fill_rests: bool = False
) -> list[Bar]:
    bars = []
    for number, ((start, length), bar_events) in enumerate(zip(spans, _place_events(events, spans)), 1):
        if fill_rests:
            bar_events = _fill_rests(bar_events, start, length)
        notes = [
            Note(
                idx=idx,
                pitch_midi=event.pitch_midi,
                name=event.name,
                start_beat=round(event.start, PRECISION),
                dur_beats=round(event.dur, PRECISION),
                tied_from_previous=event.tied_from_previous,
            )
            for idx, event in enumerate(bar_events)
        ]
        bars.append(Bar(bar=number, start_beat=round(start, PRECISION), beats=round(length, PRECISION), notes=notes))
    return bars
