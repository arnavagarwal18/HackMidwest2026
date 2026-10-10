import pytest

from app.score.bars import RawEvent, build_bars, round_to_16th, synthesize_spans


def test_round_to_16th():
    assert round_to_16th(0.979) == 1.0
    assert round_to_16th(2.0417) == 2.0
    assert round_to_16th(0.8333) == 0.75
    assert round_to_16th(4.2708) == 4.25


def test_synthesize_spans_covers_end():
    assert synthesize_spans(4, 8) == [(0, 4), (4, 4)]
    assert synthesize_spans(3, 3.25) == [(0, 3), (3, 3)]
    assert synthesize_spans(4, 0.5) == [(0, 4)]


def test_note_crossing_barline_is_split_and_tied():
    events = [RawEvent(2, 4, 60, "C4")]
    bars = build_bars(events, [(0, 4), (4, 4)])
    first, second = bars[0].notes[0], bars[1].notes[0]
    assert (first.start_beat, first.dur_beats, first.tied_from_previous) == (2, 2, False)
    assert (second.start_beat, second.dur_beats, second.tied_from_previous) == (4, 2, True)


def test_fill_rests_pads_empty_bar_and_gaps():
    bars = build_bars([RawEvent(1, 1, 60, "C4")], [(0, 4), (4, 4)], fill_rests=True)
    assert [(n.name, n.start_beat, n.dur_beats) for n in bars[0].notes] == [
        ("rest", 0, 1), ("C4", 1, 1), ("rest", 2, 2)]
    assert [(n.name, n.start_beat, n.dur_beats) for n in bars[1].notes] == [("rest", 4, 4)]


def test_notes_past_last_bar_stay_in_last_bar():
    bars = build_bars([RawEvent(3, 3, 60, "C4")], [(0, 4)])
    assert bars[0].notes[0].dur_beats == 3


def test_triplet_values_are_rounded():
    bars = build_bars([RawEvent(0, 1 / 3, 60, "C4")], [(0, 4)])
    assert bars[0].notes[0].dur_beats == pytest.approx(0.3333)
