from app.score.model import Bar, Note
from app.score.reading import ReadBar, ReadNote
from app.score.referee.checks import check_homr_bar, check_reader_bar, pitch_midi

FOUR_FOUR = (4, 4)


def homr_bar(notes: list[tuple[str, float]], number=2) -> Bar:
    built = [Note(i, None if name == "rest" else 60, name, float(i), beats) for i, (name, beats) in enumerate(notes)]
    return Bar(bar=number, start_beat=0.0, beats=4.0, notes=built)


def reader_bar(notes: list[tuple[str, str]], number=2) -> ReadBar:
    return ReadBar(bar=number, notes=[ReadNote(name=n, length=l) for n, l in notes])


def test_four_quarters_in_four_four_is_the_right_length():
    check = check_homr_bar(homr_bar([("E5", 1.0)] * 4), FOUR_FOUR, None, is_first_bar=False)
    assert check["length_ok"] is True
    assert check["beats"] == 4.0 and check["expected_beats"] == 4.0


def test_three_quarters_is_too_short():
    check = check_homr_bar(homr_bar([("E5", 1.0)] * 3), FOUR_FOUR, None, is_first_bar=False)
    assert check["length_ok"] is False
    assert check["beats"] == 3.0


def test_first_bar_may_be_a_pickup_but_a_later_bar_may_not():
    pickup = [("E5", 1.0)]
    assert check_homr_bar(homr_bar(pickup, number=1), FOUR_FOUR, None, is_first_bar=True)["length_ok"] is True
    assert check_homr_bar(homr_bar(pickup, number=2), FOUR_FOUR, None, is_first_bar=False)["length_ok"] is False


def test_a_first_bar_longer_than_the_time_signature_is_not_a_pickup():
    assert check_homr_bar(homr_bar([("E5", 1.0)] * 5, number=1), FOUR_FOUR, None, True)["length_ok"] is False


def test_an_empty_bar_is_not_the_right_length():
    assert check_homr_bar(homr_bar([], number=1), FOUR_FOUR, None, is_first_bar=True)["length_ok"] is False


def test_other_time_signatures_set_the_expected_beats():
    check = check_reader_bar(reader_bar([("E5", "dotted half")]), (3, 4), None, False)
    assert check["length_ok"] is True and check["expected_beats"] == 3.0
    assert check_reader_bar(reader_bar([("E5", "half")] * 3), (6, 8), None, False)["length_ok"] is False


def test_pitch_above_trumpet_range_is_not_range_ok():
    check = check_homr_bar(homr_bar([("C7", 1.0)] * 4), FOUR_FOUR, None, False)
    assert check["range_ok"] is False


def test_range_edges_are_included():
    assert pitch_midi("F#3") == 54 and pitch_midi("D6") == 86
    assert check_homr_bar(homr_bar([("F#3", 2.0), ("D6", 2.0)]), FOUR_FOUR, None, False)["range_ok"] is True
    assert check_homr_bar(homr_bar([("F3", 2.0), ("D6", 2.0)]), FOUR_FOUR, None, False)["range_ok"] is False
    assert check_homr_bar(homr_bar([("E3", 2.0), ("D6", 2.0)]), FOUR_FOUR, None, False)["range_ok"] is False


def test_an_unreadable_pitch_is_not_range_ok():
    assert check_reader_bar(reader_bar([("E", "whole")]), FOUR_FOUR, None, False)["range_ok"] is False
    assert check_reader_bar(reader_bar([("???", "whole")]), FOUR_FOUR, None, False)["range_ok"] is False


def test_f_natural_in_g_major_contradicts_the_key():
    check = check_reader_bar(reader_bar([("F4", "whole")]), FOUR_FOUR, 1, False)
    assert check["key_ok"] is False
    assert check_reader_bar(reader_bar([("F#4", "whole")]), FOUR_FOUR, 1, False)["key_ok"] is True


def test_notes_against_the_key_signature_are_flagged():
    # F4 in G major contradicts the key; F#4 then F4 contradicts it too, since F# was carried through the bar
    assert check_reader_bar(reader_bar([("F4", "half"), ("F4", "half")]), FOUR_FOUR, 1, False)["key_ok"] is False
    assert check_reader_bar(reader_bar([("F#4", "half"), ("F#4", "half")]), FOUR_FOUR, 1, False)["key_ok"] is True
    assert check_reader_bar(reader_bar([("F#4", "half"), ("F4", "half")]), FOUR_FOUR, 1, False)["key_ok"] is False


def test_flat_keys_expect_flats_and_unknown_keys_expect_nothing():
    assert check_homr_bar(homr_bar([("Bb4", 4.0)]), FOUR_FOUR, -1, False)["key_ok"] is True
    assert check_homr_bar(homr_bar([("Eb4", 4.0)]), FOUR_FOUR, -1, False)["key_ok"] is False
    assert check_homr_bar(homr_bar([("F4", 4.0)]), FOUR_FOUR, None, False)["key_ok"] is True


def test_reader_lengths_in_words_and_an_unknown_length():
    assert check_reader_bar(reader_bar([("E5", "dotted quarter"), ("D5", "eighth"), ("C5", "half")]),
                            FOUR_FOUR, None, False)["length_ok"] is True
    unknown = check_reader_bar(reader_bar([("E5", "wobbly")]), FOUR_FOUR, None, True)
    assert unknown["length_ok"] is False


def test_rests_are_not_checked_for_range_or_key():
    check = check_reader_bar(reader_bar([("rest", "whole")]), FOUR_FOUR, 1, False)
    assert check["length_ok"] and check["range_ok"] and check["key_ok"]
