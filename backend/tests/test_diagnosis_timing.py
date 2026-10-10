import pytest

from app import store
from app.diagnosis.problems import bar_problems
from app.diagnosis.take_alignment import align_take
from app.diagnosis.timing import (
    add_timing,
    clean_tempo_for,
    drift_label,
    error_rate,
    save_clean_tempo,
    timing_flag,
)
from diagnosis_samples import SCALE_BARS, make_scale_score, make_score, make_take, perfect_played, played_note

SCALE_MIDIS = [midi for bar in SCALE_BARS for midi in bar]


def run(score, played, take, transposition=0):
    return add_timing(align_take(score, played, take, transposition), played, take)


def bar(result: dict, number: int) -> dict:
    return next(b for b in result["bars"] if b["bar"] == number)


def flags(result: dict, bar_number: int) -> list[str | None]:
    return [timing_flag(n["timing_ms"]) for n in result["notes"] if n["bar"] == bar_number]


def test_late_notes_in_bar_three():
    played = perfect_played(SCALE_MIDIS)
    for index in range(8, 12):  # bar 3
        played[index]["onset_s"] += 0.1

    result = run(make_scale_score(), played, make_take())

    bar_three = [n for n in result["notes"] if n["bar"] == 3]
    assert [n["timing_ms"] for n in bar_three] == [pytest.approx(100)] * 4
    assert flags(result, 3) == ["late"] * 4
    assert bar(result, 3)["mean_timing_ms"] == pytest.approx(100)
    assert [n["timing_ms"] for n in result["notes"] if n["bar"] != 3] == [pytest.approx(0)] * 12
    assert flags(result, 1) == [None] * 4
    assert result["error_rate"] == pytest.approx(4 / 16)


def test_latency_is_taken_off_the_timing_on_a_metronome_grid():
    # Bar 3 is 100 ms late; the calibration says every note is heard 100 ms after it was played.
    played = perfect_played(SCALE_MIDIS)
    for index in range(8, 12):
        played[index]["onset_s"] += 0.1

    result = run(make_scale_score(), played, make_take(latency_s=0.1))

    assert result["grid"]["offset_s"] == pytest.approx(1.0)
    assert result["latency_ms"] == pytest.approx(100)
    assert [n["timing_ms"] for n in result["notes"] if n["bar"] == 3] == [pytest.approx(0)] * 4
    assert [n["timing_ms"] for n in result["notes"] if n["bar"] != 3] == [pytest.approx(-100)] * 12
    assert "late" not in [timing_flag(n["timing_ms"]) for n in result["notes"]]


def test_a_take_delayed_only_by_the_latency_is_on_time():
    played = perfect_played(SCALE_MIDIS, offset_s=1.1)

    result = run(make_scale_score(), played, make_take(latency_s=0.1))

    assert all(n["timing_ms"] == pytest.approx(0) for n in result["notes"])
    assert result["error_rate"] == 0


def test_rushing_bars_five_and_six():
    score = make_score([[60, 62, 64, 65]] * 6)
    midis = [60, 62, 64, 65] * 2
    played = perfect_played(midis, offset_s=1.0, sec_per_beat=0.5 / 1.1)  # 10% faster than 120 BPM

    result = run(score, played, make_take(bar_from=5, bar_to=6))

    assert [b["bar"] for b in result["bars"]] == [5, 6]
    for bar_result in result["bars"]:
        assert bar_result["drift"] == "rushing"
        assert bar_result["drift_pct"] == pytest.approx(10, abs=0.1)
        assert bar_result["local_bpm"] == pytest.approx(132, abs=0.2)
    assert result["played_bpm"] == pytest.approx(132, abs=0.2)
    assert result["target_bpm"] == 120


def test_fitted_grid_for_an_upload_take():
    played = perfect_played(SCALE_MIDIS, offset_s=2.3, sec_per_beat=60 / 90)

    result = run(make_scale_score(), played, make_take(downbeat_s=None, tempo_bpm=80))

    assert result["grid"]["kind"] == "fitted"
    assert result["played_bpm"] == pytest.approx(90, abs=0.1)
    assert all(abs(n["timing_ms"]) < 1 for n in result["notes"])
    assert result["error_rate"] == 0


def test_fitted_grid_does_not_subtract_latency_again():
    played = perfect_played(SCALE_MIDIS, offset_s=2.3, sec_per_beat=60 / 90)

    result = run(make_scale_score(), played, make_take(downbeat_s=None, tempo_bpm=80, latency_s=0.1))

    assert result["grid"]["kind"] == "fitted"
    assert all(abs(n["timing_ms"]) < 1 for n in result["notes"])
    assert result["latency_ms"] == pytest.approx(100)


def test_steady_bar_on_target():
    result = run(make_scale_score(), perfect_played(SCALE_MIDIS), make_take())

    assert all(b["drift"] == "steady" for b in result["bars"])
    assert bar(result, 1) == {
        "id": "b:t1:1",
        "bar": 1,
        "expected": 4,
        "ok": 4,
        "wrong": 0,
        "missed": 0,
        "extra": 0,
        "uncertain": 0,
        "mean_timing_ms": pytest.approx(0, abs=0.01),
        "local_bpm": pytest.approx(120),
        "drift_pct": pytest.approx(0, abs=0.01),
        "drift": "steady",
    }


def test_only_ok_and_wrong_notes_get_timing_and_bars_count_statuses():
    midis = list(SCALE_MIDIS)
    midis[5] = 70  # bar 2: expected 69, played a semitone up -> wrong
    played = perfect_played(midis)
    played[6] = played_note(6, 1.0 + 6 * 0.5, 74, confidence=0.2)  # expected 71 -> uncertain
    del played[4]  # bar 2's 67 is missed
    played.append(played_note(99, 1.0 + 7.5 * 0.5, 50))  # an Extra in bar 2

    result = run(make_scale_score(), played, make_take())

    status_timing = {n["status"]: n["timing_ms"] for n in result["notes"] if n["bar"] == 2}
    assert status_timing["wrong"] == pytest.approx(0)
    assert status_timing["uncertain"] is None
    assert status_timing["missed"] is None
    bar_two = bar(result, 2)
    assert (bar_two["expected"], bar_two["ok"], bar_two["wrong"], bar_two["missed"]) == (4, 1, 1, 1)
    assert (bar_two["uncertain"], bar_two["extra"]) == (1, 1)
    assert bar_two["mean_timing_ms"] == pytest.approx(0, abs=0.01)
    assert bar_two["local_bpm"] is None and bar_two["drift_pct"] is None and bar_two["drift"] is None


def test_bar_with_one_ok_note_has_no_tempo():
    played = perfect_played(SCALE_MIDIS)[:13]  # bar 4 keeps one note

    result = run(make_scale_score(), played, make_take())

    assert bar(result, 4)["ok"] == 1
    assert bar(result, 4)["drift"] is None
    assert bar(result, 4)["mean_timing_ms"] == pytest.approx(0, abs=0.01)


def test_missing_played_note_is_rejected():
    played = perfect_played(SCALE_MIDIS)
    result = align_take(make_scale_score(), played, make_take(), 0)

    with pytest.raises(ValueError, match="not in the played notes"):
        add_timing(result, played[:5], make_take())


@pytest.mark.parametrize(
    "ms, flag", [(80, None), (80.5, "late"), (-80, None), (-80.5, "early"), (0, None), (None, None)]
)
def test_late_and_early_threshold(ms, flag):
    assert timing_flag(ms) == flag


@pytest.mark.parametrize(
    "pct, label", [(5, "steady"), (5.1, "rushing"), (-5, "steady"), (-5.1, "dragging"), (None, None)]
)
def test_drift_label(pct, label):
    assert drift_label(pct) == label


def note(status, timing_ms=None):
    return {"status": status, "timing_ms": timing_ms}


def test_error_rate_counts_wrong_missed_late_early_and_leaves_uncertain_out():
    notes = [
        note("ok", 0),
        note("ok", 10),
        note("wrong", 0),
        note("missed"),
        note("ok", 120),
        note("ok", -120),
        note("uncertain"),
        note("uncertain"),
    ]

    assert error_rate(notes) == pytest.approx(4 / 6)


def test_error_rate_is_none_when_nothing_can_be_judged():
    assert error_rate([note("uncertain")]) is None
    assert error_rate([]) is None


def diagnosis(played_bpm, rate, cant_tell=False):
    return {"played_bpm": played_bpm, "error_rate": rate, "cant_tell": cant_tell}


def stored_take(take_id, played_bpm, rate, cant_tell=False, bars=(1, 4)):
    return {
        "take_id": take_id,
        "bar_from": bars[0],
        "bar_to": bars[1],
        "diagnosis": diagnosis(played_bpm, rate, cant_tell),
    }


def test_clean_tempo_is_the_highest_clean_played_bpm_on_the_range():
    takes = {
        "t1": stored_take("t1", 80, 0.05),
        "t2": stored_take("t2", 100, 0.10),
        "t3": stored_take("t3", 120, 0.30),  # too many errors
        "t4": stored_take("t4", 130, 0.0, cant_tell=True),
        "t5": stored_take("t5", 140, 0.0, bars=(1, 2)),  # another range
        "t6": {"take_id": "t6", "bar_from": 1, "bar_to": 4},  # not diagnosed yet
    }
    current = {"take_id": "t7", "bar_from": 1, "bar_to": 4}

    assert clean_tempo_for(takes, current, diagnosis(90, 0.02)) == 100
    assert clean_tempo_for(takes, current, diagnosis(110, 0.02)) == 110


def test_clean_tempo_falls_back_to_70_percent_of_this_take():
    takes = {"t1": stored_take("t1", 120, 0.5)}
    current = {"take_id": "t2", "bar_from": 1, "bar_to": 4}

    assert clean_tempo_for(takes, current, diagnosis(90, 0.4)) == pytest.approx(63)
    assert clean_tempo_for(takes, current, diagnosis(90, None)) == pytest.approx(63)
    assert clean_tempo_for(takes, current, diagnosis(90, 0.0, cant_tell=True)) == pytest.approx(63)


def test_save_clean_tempo_stores_it_under_the_bar_range(sessions_root):
    session = store.create("violin")
    store.update(session.session_id, "takes", {"t1": stored_take("t1", 100, 0.0, bars=(3, 6))})
    take = {"take_id": "t2", "bar_from": 3, "bar_to": 6}

    assert save_clean_tempo(session.session_id, take, diagnosis(90, 0.0)) == 100
    assert save_clean_tempo(session.session_id, {**take, "bar_from": 1}, diagnosis(80, 0.9)) == pytest.approx(56)

    store._sessions.clear()  # read it back from disk
    assert store.get(session.session_id).clean_tempo == {"3-6": 100, "1-6": pytest.approx(56)}


def test_missing_repeated_note_is_missed_and_the_played_one_pairs_with_its_own_time():
    # Bar 2 is F F E E. The first E is not played; the second E comes on time (beat 7). It must pair with
    # the second expected E, not the first (which would read as 663 ms late and a dragging bar).
    score = make_score([[60, 62, 64, 65], [65, 65, 64, 64], [67, 69, 71, 72], [72, 71, 69, 67]])
    midis = [60, 62, 64, 65, 65, 65, 64, 64, 67, 69, 71, 72, 72, 71, 69, 67]
    played = [p for p in perfect_played(midis) if p["i"] != 6]

    result = run(score, played, make_take())

    by_id = {n["id"]: n for n in result["notes"]}
    assert by_id["n:t1:2:2"]["status"] == "missed"
    assert by_id["n:t1:2:3"]["status"] == "ok"
    assert by_id["n:t1:2:3"]["played_i"] == 7
    assert by_id["n:t1:2:3"]["timing_ms"] == pytest.approx(0)
    assert [timing_flag(n["timing_ms"]) for n in result["notes"] if n["bar"] == 2] == [None] * 4
    assert bar(result, 2)["drift_pct"] == pytest.approx(0)
    assert {p.kind for p in bar_problems(result)} == {"notes"}
