import pytest

from app.diagnosis.take_alignment import align_take
from diagnosis_samples import SCALE_BARS, make_scale_score, make_take, perfect_played, played_note

SCALE_MIDIS = [midi for bar in SCALE_BARS for midi in bar]


def played_with_offsets(offsets: dict[int, float], default: float = 0.0) -> list[dict]:
    """The scale in perfect time, each note's pitch shifted by `offsets[index]` (else `default`) semitones."""
    return [
        played_note(i, 1.0 + i * 0.5, midi + offsets.get(i, default))
        for i, midi in enumerate(SCALE_MIDIS)
    ]


def diagnose(played: list[dict]) -> dict:
    return align_take(make_scale_score(), played, make_take(), 0)


def statuses(result: dict) -> list[str]:
    return [note["status"] for note in result["notes"]]


def test_a_player_tuned_sharp_is_judged_against_their_own_tuning():
    result = diagnose(played_with_offsets({7: 0.52}, default=0.25))

    assert result["tuning_cents"] == 25
    assert statuses(result) == ["ok"] * 16
    assert result["notes"][0]["cents_off"] == pytest.approx(0)
    assert result["notes"][7]["cents_off"] == pytest.approx(27)


def test_a_flat_player_gets_a_negative_tuning():
    result = diagnose(played_with_offsets({}, default=-0.3))

    assert result["tuning_cents"] == -30
    assert statuses(result) == ["ok"] * 16


def test_with_fewer_than_five_in_tune_pairs_the_tuning_is_zero_and_marking_is_unchanged():
    four_sharp_notes = [played_note(i, 1.0 + i * 0.5, midi + 0.25) for i, midi in enumerate(SCALE_MIDIS[:4])]

    result = align_take(make_scale_score(), four_sharp_notes, make_take(bar_to=1), 0)

    assert result["tuning_cents"] == 0
    assert statuses(result) == ["ok"] * 4
    assert result["notes"][0]["cents_off"] == pytest.approx(25)


def test_a_sharp_note_beyond_half_a_semitone_stays_wrong_without_enough_in_tune_pairs():
    four_notes = [played_note(i, 1.0 + i * 0.5, midi + 0.25) for i, midi in enumerate(SCALE_MIDIS[:4])]
    four_notes[3] = played_note(3, 2.5, SCALE_MIDIS[3] + 0.6)

    result = align_take(make_scale_score(), four_notes, make_take(bar_to=1), 0)

    assert result["tuning_cents"] == 0
    assert statuses(result) == ["ok"] * 3 + ["wrong"]


def test_the_tuning_offset_is_clamped_to_forty_cents():
    result = diagnose(played_with_offsets({}, default=0.45))

    assert result["tuning_cents"] == 40
    assert statuses(result) == ["ok"] * 16
    assert result["notes"][0]["cents_off"] == pytest.approx(5)


def test_a_full_semitone_error_is_still_wrong_under_a_tuning_offset():
    result = diagnose(played_with_offsets({3: 1.25}, default=0.25))

    assert result["tuning_cents"] == 25
    assert statuses(result).count("wrong") == 1
    assert result["notes"][3]["status"] == "wrong"


def test_a_perfectly_tuned_take_has_zero_tuning():
    result = diagnose(perfect_played(SCALE_MIDIS))

    assert result["tuning_cents"] == 0
