import pytest

from app.score.builtins import BUILTINS_DIR, builtin_path, list_builtins
from app.score.exceptions import BuiltinNotFound
from app.score.parse import parse_score_file

EXPECTED = {
    "ode_to_joy": (16, "E4", None),
    "twinkle": (12, "C4", None),
    "ode_to_joy_trumpet": (16, "F#4", -2),
    "twinkle_trumpet": (12, "D4", -2),
}


def test_listing_has_the_four_pieces():
    assert {p["piece_id"] for p in list_builtins()} == set(EXPECTED)


@pytest.mark.parametrize("instrument, count", [("violin", 2), ("trumpet", 2), ("cello", 0)])
def test_listing_filters_by_instrument(instrument, count):
    assert len(list_builtins(instrument)) == count


@pytest.mark.parametrize("piece_id, expected", EXPECTED.items())
def test_each_builtin_parses_to_its_listed_bars_and_first_note(piece_id, expected):
    bars, first_note, transpose = expected
    listed = next(p for p in list_builtins() if p["piece_id"] == piece_id)
    score = parse_score_file(builtin_path(piece_id))
    assert listed["bars"] == len(score.bars) == bars
    assert score.bars[0].notes[0].name == first_note
    assert score.written_transpose_semitones == transpose
    assert score.warnings == []


def test_trumpet_builtins_have_written_transpose_minus_two():
    for piece in list_builtins("trumpet"):
        assert parse_score_file(builtin_path(piece["piece_id"])).written_transpose_semitones == -2


def test_unknown_piece_is_not_found():
    with pytest.raises(BuiltinNotFound):
        builtin_path("../../etc/passwd")


def test_every_listed_piece_has_a_file():
    for piece in list_builtins():
        assert (BUILTINS_DIR / f"{piece['piece_id']}.musicxml").is_file()
