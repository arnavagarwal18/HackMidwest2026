import pytest

from app.score.compare import MOSTLY_DIFFERENT_WARNING, NO_NOTES_TEXT, NO_READING_WARNING, compare_bars
from app.score.model import Bar, Note, Score
from app.score.note_text import normalise_length, normalise_name
from app.score.reading import ReadBar, ReadNote, Reading

QUARTER, HALF = 1.0, 2.0
BAR_NOTES = {
    1: [("E5", QUARTER, "quarter"), ("D5", QUARTER, "quarter"), ("C5", HALF, "half")],
    2: [("rest", QUARTER, "quarter"), ("Bb4", 1.5, "dotted quarter"), ("A4", 0.5, "eighth"), ("G4", HALF, "half")],
    3: [("C5", QUARTER, "quarter"), ("E5", QUARTER, "quarter"), ("G5", HALF, "half")],
    4: [("C5", 4.0, "whole")],
}


def make_score(bar_numbers=(1, 2, 3, 4)) -> Score:
    bars = []
    for number in bar_numbers:
        notes = [
            Note(idx=i, pitch_midi=None if name == "rest" else 60, name=name, start_beat=0.0, dur_beats=beats)
            for i, (name, beats, _) in enumerate(BAR_NOTES[number])
        ]
        bars.append(Bar(bar=number, start_beat=(number - 1) * 4.0, beats=4.0, notes=notes))
    return Score("t", "flute", 90.0, (4, 4), None, bars)


def make_reading(bar_numbers=(1, 2, 3, 4), changes=None) -> Reading:
    changes = changes or {}
    bars = []
    for number in bar_numbers:
        notes = changes.get(number) or [(name, length) for name, _, length in BAR_NOTES[number]]
        bars.append(ReadBar(bar=number, notes=[ReadNote(name=n, length=l) for n, l in notes]))
    return Reading(bars=bars)


def test_identical_readings_have_no_doubtful_bars():
    result = compare_bars(make_score(), make_reading())
    assert result.doubtful_bars == []
    assert result.double_checked is True
    assert result.warnings == []


def test_one_changed_pitch_lists_exactly_that_bar():
    reading = make_reading(changes={3: [("C5", "quarter"), ("F5", "quarter"), ("G5", "half")]})
    result = compare_bars(make_score(), reading)
    assert result.doubtful_bars == [
        {"bar": 3, "homr_text": "C5 quarter, E5 quarter, G5 half", "reader_text": "C5 quarter, F5 quarter, G5 half"}
    ]
    assert result.double_checked is True


def test_changed_length_and_changed_note_count_are_doubtful():
    reading = make_reading(changes={1: [("E5", "quarter"), ("D5", "quarter"), ("C5", "quarter")], 4: [("C5", "half"), ("C5", "half")]})
    result = compare_bars(make_score(), reading)
    assert [d["bar"] for d in result.doubtful_bars] == [1, 4]
    assert result.doubtful_bars[1]["reader_text"] == "C5 half, C5 half"


def test_bar_missing_from_reader_is_listed_with_no_reader_text():
    result = compare_bars(make_score(), make_reading(bar_numbers=(1, 2, 4)))
    assert result.doubtful_bars == [{"bar": 3, "homr_text": "C5 quarter, E5 quarter, G5 half", "reader_text": None}]
    assert result.double_checked is True


def test_extra_reader_bar_is_listed_as_no_notes_read():
    result = compare_bars(make_score(bar_numbers=(1, 2, 3)), make_reading())
    assert result.doubtful_bars == [{"bar": 4, "homr_text": NO_NOTES_TEXT, "reader_text": "C5 whole"}]
    assert result.double_checked is True


def test_more_than_half_different_gives_empty_list_and_warning():
    different = {n: [("A3", "whole")] for n in (1, 2, 3)}
    result = compare_bars(make_score(), make_reading(changes=different))
    assert result.doubtful_bars == []
    assert result.double_checked is False
    assert result.warnings == [MOSTLY_DIFFERENT_WARNING]


def test_exactly_half_different_is_still_reported_bar_by_bar():
    different = {n: [("A3", "whole")] for n in (1, 2)}
    result = compare_bars(make_score(), make_reading(changes=different))
    assert [d["bar"] for d in result.doubtful_bars] == [1, 2]
    assert result.double_checked is True


@pytest.mark.parametrize("reading", [None, Reading(bars=[])])
def test_no_reading_means_not_double_checked(reading):
    result = compare_bars(make_score(), reading)
    assert (result.doubtful_bars, result.double_checked, result.warnings) == ([], False, [NO_READING_WARNING])


def test_spelling_variants_of_the_same_note_are_not_doubtful():
    reading = make_reading(
        changes={
            1: [("e5", "Quarter"), ("D5", "crotchet"), ("C5", "minim")],
            2: [("Rest", "quarter"), ("B♭4", "dotted quarter"), ("A4", "8th"), ("G4", "half note")],
            3: [("c5", "quarter"), ("E5", "quarter"), ("G5", "half")],
            4: [("C5", "semibreve")],
        }
    )
    assert compare_bars(make_score(), reading).doubtful_bars == []


def test_a_different_octave_is_doubtful():
    reading = make_reading(changes={4: [("C4", "whole")]})
    assert [d["bar"] for d in compare_bars(make_score(), reading).doubtful_bars] == [4]


def test_tied_continuation_stays_a_separate_note():
    score = make_score()
    score.bars[3].notes = [
        Note(0, 60, "C5", 0.0, 2.0),
        Note(1, 60, "C5", 2.0, 2.0, tied_from_previous=True),
    ]
    reading = make_reading(changes={4: [("C5", "half"), ("C5", "half")]})
    assert compare_bars(score, reading).doubtful_bars == []


@pytest.mark.parametrize(
    "raw, expected",
    [("B-4", "Bb4"), ("B♭4", "Bb4"), ("b flat 4", "Bb4"), ("F♯3", "F#3"), ("A♮3", "A3"), ("pause", "rest"), ("e5", "E5"), ("H4", "H4")],
)
def test_normalise_name(raw, expected):
    assert normalise_name(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("sixteenth", "16th"), ("16th", "16th"), ("Dotted Quarter", "dotted quarter"), ("quarter dotted", "dotted quarter"), ("eighth.", "dotted eighth"), ("triplet", "triplet")],
)
def test_normalise_length(raw, expected):
    assert normalise_length(raw) == expected


def test_a_triplet_duration_never_matches_a_reader_length():
    score = make_score()
    score.bars[0].notes = [Note(0, 60, "C5", 0.0, 0.3333)]
    reading = make_reading(changes={1: [("C5", "eighth")]})
    assert compare_bars(score, reading).doubtful_bars == [{"bar": 1, "homr_text": "C5 0.3333 beats", "reader_text": "C5 eighth"}]
