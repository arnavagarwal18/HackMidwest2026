import random

import pytest

from app.errors import AppError
from app.diagnosis.errors import DiagnosisInputError
from app.diagnosis.expected import build_expected_notes
from app.diagnosis.rank import rank
from app.diagnosis.take_alignment import align_take
from app.diagnosis.timing import add_timing
from diagnosis_samples import (
    SCALE_BARS,
    make_scale_score,
    make_score,
    make_take,
    perfect_played,
    played_note,
)

SCALE_MIDIS = [midi for bar in SCALE_BARS for midi in bar]


def statuses(result: dict) -> list[str]:
    return [note["status"] for note in result["notes"]]


def test_perfect_take_is_all_ok():
    result = align_take(make_scale_score(), perfect_played(SCALE_MIDIS), make_take(), 0)

    assert statuses(result) == ["ok"] * 16
    assert result["alignment_quality"] == 1.0
    assert result["extras"] == []
    assert result["cant_tell"] is False
    assert result["cant_tell_reason"] is None
    assert result["grid"] == {"kind": "metronome", "offset_s": 1.0, "sec_per_beat": 0.5}
    assert result["fit"]["sec_per_beat"] == pytest.approx(0.5)
    first = result["notes"][0]
    assert first["id"] == "n:t1:1:0"
    assert first["expected_onset_s"] == 1.0
    assert first["played_i"] == 0
    assert first["cents_off"] == 0
    assert first["timing_ms"] is None


def test_wrong_missed_and_extra_in_bar_two():
    # Bar 2 is expected 67 69 71 72 at beats 4-7. Leave out the 67, play 70 (a semitone up from 69),
    # 71, 72, then a stray 50 at beat 7.5.
    played_spec = [(0, 60), (1, 62), (2, 64), (3, 65), (5, 70), (6, 71), (7, 72), (7.5, 50)]
    played_spec += [(8, 72), (9, 71), (10, 69), (11, 67), (12, 65), (13, 64), (14, 62), (15, 60)]
    played = [played_note(i, 1.0 + beat * 0.5, midi) for i, (beat, midi) in enumerate(played_spec)]

    result = align_take(make_scale_score(), played, make_take(), 0)

    by_id = {note["id"]: note for note in result["notes"]}
    assert by_id["n:t1:2:1"]["status"] == "wrong"
    assert by_id["n:t1:2:1"]["played_name"] == "A#4"
    assert by_id["n:t1:2:1"]["cents_off"] == 100
    assert by_id["n:t1:2:0"]["status"] == "missed"
    assert by_id["n:t1:2:0"]["played_i"] is None
    assert by_id["n:t1:2:0"]["cents_off"] is None
    assert [note["status"] for note in result["notes"] if note["bar"] != 2] == ["ok"] * 12
    assert result["extras"] == [
        {"id": "x:t1:7", "played_i": 7, "bar": 2, "onset_s": 4.75, "played_name": "D3", "confidence": 1.0}
    ]
    assert result["alignment_quality"] == pytest.approx(14 / 16)
    assert result["cant_tell"] is False


def test_low_confidence_mismatch_is_uncertain():
    midis = list(SCALE_MIDIS)
    midis[5] = 74  # expected 69
    played = perfect_played(midis)
    played[5] = played_note(5, 3.5, 74, confidence=0.3)

    result = align_take(make_scale_score(), played, make_take(), 0)

    assert result["notes"][5]["status"] == "uncertain"
    assert result["notes"][5]["confidence"] == 0.3
    assert statuses(result).count("ok") == 15


def test_in_tune_note_is_ok_even_when_confidence_is_low():
    played = perfect_played(SCALE_MIDIS)
    played[2] = played_note(2, 2.0, 64.4, confidence=0.1)

    result = align_take(make_scale_score(), played, make_take(), 0)

    assert result["notes"][2]["status"] == "ok"
    assert result["notes"][2]["cents_off"] == pytest.approx(40)


def test_low_confidence_stray_note_is_dropped():
    played = perfect_played(SCALE_MIDIS) + [played_note(99, 20.0, 40, confidence=0.4)]

    result = align_take(make_scale_score(), played, make_take(), 0)

    assert result["extras"] == []
    assert statuses(result) == ["ok"] * 16


def test_random_notes_cant_tell():
    rng = random.Random(7)
    played = [played_note(i, 1.0 + i * 0.5, rng.randint(30, 90)) for i in range(16)]

    result = align_take(make_scale_score(), played, make_take(), 0)

    assert result["cant_tell"] is True
    assert result["cant_tell_reason"] in ("low_match", "few_pairs")
    assert result["alignment_quality"] < 0.4


def test_silence_cant_tell():
    result = align_take(make_scale_score(), [], make_take(), 0)

    assert statuses(result) == ["missed"] * 16
    assert result["cant_tell_reason"] == "low_match"
    assert result["grid"]["kind"] == "metronome"


def test_few_pairs_when_most_expected_notes_have_no_partner():
    # 7 of 16 notes are played, spread over all four bars: 7 pairs is under half of the expected notes, and
    # quality is 7/16 (the played window is every bar, so nothing is "not played").
    played = [p for p in perfect_played(SCALE_MIDIS) if p["i"] in (0, 1, 2, 5, 9, 13, 15)]
    result = align_take(make_scale_score(), played, make_take(), 0)

    assert result["alignment_quality"] == pytest.approx(7 / 16)
    assert result["cant_tell"] is True
    assert result["cant_tell_reason"] == "few_pairs"


def test_two_note_range_is_too_short():
    score = make_score([[60, 62, None, None]])

    result = align_take(score, perfect_played([60, 62]), make_take(bar_from=1, bar_to=1), 0)

    assert statuses(result) == ["ok", "ok"]
    assert result["cant_tell"] is True
    assert result["cant_tell_reason"] == "too_short"


def test_unknown_downbeat_uses_fitted_grid():
    played = perfect_played(SCALE_MIDIS, offset_s=2.3, sec_per_beat=60 / 90)

    result = align_take(make_scale_score(), played, make_take(downbeat_s=None, tempo_bpm=90), 0)

    assert result["grid"]["kind"] == "fitted"
    assert result["grid"]["sec_per_beat"] == pytest.approx(60 / 90)
    assert result["grid"]["offset_s"] == pytest.approx(2.3)
    assert result["notes"][0]["expected_onset_s"] == pytest.approx(2.3)
    assert statuses(result) == ["ok"] * 16


def test_fitted_grid_without_enough_pairs_falls_back_to_target_tempo():
    played = perfect_played([60, 62], offset_s=2.0)

    result = align_take(make_scale_score(), played, make_take(downbeat_s=None), 0)

    assert result["fit"] is None
    assert result["grid"]["kind"] == "fitted"
    assert result["grid"]["sec_per_beat"] == pytest.approx(0.5)
    assert result["grid"]["offset_s"] == pytest.approx(2.0)


def test_metronome_grid_starts_at_the_downbeat_whatever_the_latency():
    result = align_take(make_scale_score(), perfect_played(SCALE_MIDIS), make_take(latency_s=0.12), 0)

    assert result["grid"]["offset_s"] == pytest.approx(1.0)


def test_pass_two_rejects_pairs_far_from_the_fitted_time():
    # The last played note comes 3 beats later than it should: pass 2 won't pair it with the last
    # expected note, so that one is missed. It is also more than a beat past the last paired note's end,
    # so it counts as outside the range, not as an Extra.
    played = perfect_played(SCALE_MIDIS)
    played[15] = played_note(15, 1.0 + 18 * 0.5, 60)

    result = align_take(make_scale_score(), played, make_take(), 0)

    assert result["notes"][15]["status"] == "missed"
    assert result["extras"] == []
    assert result["outside_count"] == 1


def test_played_notes_are_lined_up_in_time_order():
    played = list(reversed(perfect_played(SCALE_MIDIS)))

    result = align_take(make_scale_score(), played, make_take(), 0)

    assert statuses(result) == ["ok"] * 16
    assert result["notes"][0]["played_i"] == 0


def test_tied_notes_merge_into_one_expected_note():
    score = make_score([[60, 62, None, 64], [(64, "tied"), 65, (65, "tied"), (65, "tied")]])

    expected = build_expected_notes(score, "t1", 1, 2, 0)

    assert [(note.id, note.midi, note.onset_beats, note.dur_beats) for note in expected] == [
        ("n:t1:1:0", 60, 0.0, 1.0),
        ("n:t1:1:1", 62, 1.0, 1.0),
        ("n:t1:1:3", 64, 3.0, 2.0),
        ("n:t1:2:1", 65, 5.0, 3.0),
    ]


def test_rest_between_same_pitches_breaks_a_tie():
    score = make_score([[60, None, (60, "tied"), 62]])

    expected = build_expected_notes(score, "t1", 1, 1, 0)

    assert [note.id for note in expected] == ["n:t1:1:0", "n:t1:1:2", "n:t1:1:3"]


def test_expected_onsets_count_from_the_first_bar_of_the_range():
    expected = build_expected_notes(make_scale_score(), "t1", 2, 3, 0)

    assert expected[0].id == "n:t1:2:0"
    assert expected[0].onset_beats == 0.0
    assert expected[-1].onset_beats == 7.0
    assert len(expected) == 8


def test_transposition_gives_sounding_pitch_and_name():
    expected = build_expected_notes(make_score([[62, 64, 65, 67]]), "t1", 1, 1, -2)

    assert [(note.midi, note.name) for note in expected] == [(60, "C4"), (62, "D4"), (63, "D#4"), (65, "F4")]


def test_transposed_take_marks_against_sounding_pitch():
    written = make_score([[62, 64, 66, 67]])

    result = align_take(written, perfect_played([60, 62, 64, 65]), make_take(bar_to=1), -2)

    assert statuses(result) == ["ok"] * 4
    assert [note["expected_midi"] for note in result["notes"]] == [60, 62, 64, 65]


@pytest.mark.parametrize(
    "take_overrides, message",
    [
        ({"bar_to": 9}, "no bar"),
        ({"bar_from": 3, "bar_to": 2}, "backwards"),
        ({"tempo_bpm": 0}, "tempo_bpm"),
    ],
)
def test_bad_input_raises_readable_error(take_overrides, message):
    with pytest.raises(DiagnosisInputError, match=message):
        align_take(make_scale_score(), perfect_played(SCALE_MIDIS), make_take(**take_overrides), 0)


def test_input_error_is_a_422_app_error():
    with pytest.raises(DiagnosisInputError) as raised:
        align_take(make_scale_score(), [], make_take(bar_to=9), 0)

    assert isinstance(raised.value, AppError)
    assert (raised.value.status, raised.value.code) == (422, "bad_diagnosis_input")


def test_missing_played_field_raises_readable_error():
    with pytest.raises(DiagnosisInputError, match="missing"):
        align_take(make_scale_score(), [{"i": 0, "onset_s": 1.0}], make_take(), 0)


def test_missing_take_field_raises_readable_error():
    with pytest.raises(DiagnosisInputError, match="take is missing"):
        align_take(make_scale_score(), [], {"take_id": "t1"}, 0)


def two_bar_played_with_outside_notes() -> list[dict]:
    """8 correct notes from 4.0 s (0.5 s a beat), 3 notes from 3 beats before them, 10 from 2 beats after the last ends."""
    offset_s, beat_s = 4.0, 0.5
    before = [(-3 + 0.5 * n, 70 + n) for n in range(3)]
    on_grid = [(beat, midi) for beat, midi in enumerate(SCALE_MIDIS[:8])]
    after = [(10 + 0.5 * n, 70 + n) for n in range(10)]
    spec = sorted(before + on_grid + after)
    return [played_note(i, offset_s + beat * beat_s, midi) for i, (beat, midi) in enumerate(spec)]


def test_notes_far_outside_the_chosen_bars_are_counted_not_extras():
    take = make_take(bar_to=2, downbeat_s=4.0)

    result = align_take(make_scale_score(), two_bar_played_with_outside_notes(), take, 0)
    timed = add_timing(result, two_bar_played_with_outside_notes(), take)

    assert statuses(result) == ["ok"] * 8
    assert result["extras"] == []
    assert result["outside_count"] == 13
    assert timed["error_rate"] == 0
    assert [bar["extra"] for bar in timed["bars"]] == [0, 0]
    problems = rank("t1", timed, [])["problems"]
    assert [problem for problem in problems if problem["kind"] == "notes"] == []


def test_a_single_unmatched_note_between_matched_notes_is_still_an_extra():
    spec = [(0, 60), (1, 62), (2, 64), (2.5, 50), (3, 65), (4, 67), (5, 69), (6, 71), (7, 72)]
    played = [played_note(i, 1.0 + beat * 0.5, midi) for i, (beat, midi) in enumerate(spec)]

    result = align_take(make_scale_score(), played, make_take(bar_to=2), 0)

    assert [extra["id"] for extra in result["extras"]] == ["x:t1:3"]
    assert result["outside_count"] == 0
