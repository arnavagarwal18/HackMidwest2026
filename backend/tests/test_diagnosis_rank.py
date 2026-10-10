import pytest

from app import diagnosis, store
from app.diagnosis.rank import rank
from app.diagnosis.sentences import sentence_text
from app.diagnosis.take_alignment import align_take
from app.diagnosis.timing import add_timing
from app.takes.take_store import get_take, update_take
from diagnosis_samples import SCALE_BARS, make_scale_score, make_score, make_take, perfect_played, played_note
from diagnosis_session import add_transcribed_take, diagnosed_session, make_session

SCALE_MIDIS = [midi for bar in SCALE_BARS for midi in bar]


def timed(played, score=None, take=None):
    take = take or make_take()
    return add_timing(align_take(score or make_scale_score(), played, take, 0), played, take)


def flag(k=0, bars=(2,), severity=0.8, confidence=0.9, **extra):
    return {
        "id": f"f:t1:{k}", "rule": "elbow_height", "label": "Elbow drops", "bars": list(bars),
        "start_s": 14.2, "end_s": 15.0, "peak_s": 14.5, "severity": severity, "confidence": confidence, **extra,
    }


def wrong_in_bar(bar: int, confidence: float, midi_shift: int = 1) -> list[dict]:
    played = perfect_played(SCALE_MIDIS)
    index = (bar - 1) * 4
    played[index] = played_note(index, played[index]["onset_s"], SCALE_MIDIS[index] + midi_shift, confidence)
    return played


def test_only_the_certain_problem_is_tier_one():
    played = wrong_in_bar(1, 0.9)
    played[8] = played_note(8, played[8]["onset_s"], SCALE_MIDIS[8] + 1, 0.5)  # bar 3, unsure about it

    ranking = rank("t1", timed(played), [])

    by_bar = {p["bars"][0]: p for p in ranking["problems"]}
    assert by_bar[1]["certainty"] == pytest.approx(0.9 * 14 / 16, abs=1e-3)
    assert by_bar[3]["certainty"] == pytest.approx(0.5 * 14 / 16, abs=1e-3)
    assert (by_bar[1]["tier"], by_bar[3]["tier"]) == (1, 2)
    assert [s["problem_id"] for s in ranking["tier1"]] == [by_bar[1]["id"]]


def test_ids_follow_the_ranking_and_score_is_size_times_certainty():
    played = wrong_in_bar(1, 0.9)
    played[8] = played_note(8, played[8]["onset_s"], SCALE_MIDIS[8] + 1, 0.6)

    problems = rank("t1", timed(played), [])["problems"]

    assert [p["id"] for p in problems] == ["p:t1:0", "p:t1:1"]
    assert [p["bars"] for p in problems] == [[1], [3]]
    assert problems[0]["score"] == pytest.approx(0.25 * 0.9 * 0.875, abs=1e-3)
    assert problems[0]["measurement_ids"] == ["n:t1:1:0"]


def test_notes_sentence_names_wrong_and_missed_notes():
    played = wrong_in_bar(1, 0.9)
    del played[1]  # the second note of bar 1 is never played

    ranking = rank("t1", timed(played), [])

    assert ranking["problems"][0]["numbers"] == {
        "wrong": 1, "missed": 1, "extra": 0, "first_wrong": {"played": "C#4", "expected": "C4"},
    }
    assert ranking["tier1"][0]["text"] == "Bar 1: 1 wrong note (played C#4 for C4) and 1 missed."
    assert ranking["tier1"][0]["jump"] == {"bar": 1, "time_s": 1.0}
    assert ranking["tier1"][0]["measurement_ids"] == ["n:t1:1:0", "n:t1:1:1"]


def test_late_notes_sentence_and_size():
    played = perfect_played(SCALE_MIDIS)
    for index in range(8, 12):
        played[index]["onset_s"] += 0.1

    problem = rank("t1", timed(played), [])["problems"][0]

    assert (problem["kind"], problem["bars"], problem["numbers"]) == ("late", [3], {"mean_ms": 100.0, "count": 4})
    assert problem["size"] == 0.5
    assert sentence_text(problem) == "Bar 3: 4 notes late, 100 ms on average."


def test_only_one_late_note_is_not_a_problem():
    played = perfect_played(SCALE_MIDIS)
    played[8]["onset_s"] += 0.1

    kinds = [p["kind"] for p in rank("t1", timed(played), [])["problems"]]
    assert "late" not in kinds  # the bar's tempo wobble is a separate, drift problem


def test_adjacent_rushing_bars_merge_and_score_gets_the_multi_bar_bonus():
    played = perfect_played(SCALE_MIDIS, sec_per_beat=0.45)  # about 11% faster than 120 BPM

    problems = rank("t1", timed(played), [])["problems"]

    rushing = next(p for p in problems if p["kind"] == "rushing")
    assert rushing["bars"] == [1, 2, 3, 4]
    assert rushing["numbers"]["drift_pct"] == pytest.approx(11.11, abs=0.01)
    assert sentence_text(rushing) == "Bars 1-4: rushing, about 11% faster than 120 BPM."
    assert rushing["score"] == pytest.approx(rushing["size"] * rushing["certainty"] * 1.75, abs=1e-3)


def test_dragging_sentence():
    played = perfect_played(SCALE_MIDIS, sec_per_beat=0.55)

    dragging = next(p for p in rank("t1", timed(played), [])["problems"] if p["kind"] == "dragging")

    assert sentence_text(dragging) == "Bars 1-4: dragging, about 9% slower than 120 BPM."


def test_extra_notes_count_in_the_notes_problem():
    played = perfect_played(SCALE_MIDIS)
    played.append(played_note(16, 1.0 + 0.25, 70, 0.9))  # between notes of bar 1

    problem = rank("t1", timed(played), [])["problems"][0]

    assert problem["numbers"]["extra"] == 1
    assert sentence_text(problem) == "Bar 1: 1 extra."
    assert problem["measurement_ids"] == ["x:t1:16"]


def test_uncertain_notes_are_never_in_a_problem():
    played = wrong_in_bar(2, 0.3)

    assert rank("t1", timed(played), [])["problems"] == []


def test_form_flag_becomes_a_problem_with_its_own_sentence():
    ranking = rank("t1", timed(perfect_played(SCALE_MIDIS)), [flag(0, bars=(2,), severity=0.6, confidence=0.7)])

    problem = ranking["problems"][0]
    assert (problem["kind"], problem["size"], problem["certainty"], problem["measurement_ids"]) == (
        "form", 0.6, 0.7, ["f:t1:0"],
    )
    assert ranking["tier1"][0]["text"] == "Bar 2, 0:14: Elbow drops."
    assert ranking["tier1"][0]["jump"] == {"bar": 2, "time_s": 14.2}


def test_form_sentence_adds_its_first_link():
    linked = [{"kind": "late", "bar": 3, "ids": ["n:t1:3:0"]}, {"kind": "notes", "bar": 4, "ids": ["n:t1:4:0"]}]

    ranking = rank("t1", timed(perfect_played(SCALE_MIDIS)), [flag(bars=(2, 3), linked=linked)])

    assert ranking["tier1"][0]["text"] == "Bars 2-3, 0:14: Elbow drops, at the same time as late in bar 3."


def test_tiers_are_three_then_seven_then_the_rest():
    flags = [flag(k, severity=0.95 - 0.05 * k) for k in range(12)]

    problems = rank("t1", timed(perfect_played(SCALE_MIDIS)), flags)["problems"]

    assert [p["tier"] for p in problems] == [1] * 3 + [2] * 7 + [3] * 2
    assert [p["measurement_ids"] for p in problems[:2]] == [["f:t1:0"], ["f:t1:1"]]


def test_low_score_or_certainty_never_reaches_tier_one():
    flags = [flag(0, severity=0.1, confidence=0.9), flag(1, severity=0.9, confidence=0.5)]

    ranking = rank("t1", timed(perfect_played(SCALE_MIDIS)), flags)

    assert [p["tier"] for p in ranking["problems"]] == [2, 2]
    assert ranking["tier1"] == []


def test_cant_tell_ranks_nothing():
    diagnosis_with_verdict = {**timed(perfect_played(SCALE_MIDIS)), "cant_tell": True}

    assert rank("t1", diagnosis_with_verdict, [flag()]) == {"problems": [], "tier1": []}


def test_rerank_adds_a_form_problem_and_renumbers_ids(sessions_root):
    session_id, take_id = diagnosed_session(wrong_in_bar(1, 0.9))
    before = get_take(session_id, take_id)["diagnosis"]
    assert [p["kind"] for p in before["problems"]] == ["notes"]

    update_take(session_id, take_id, form={"status": "ok", "flags": [flag(0, bars=(3,), severity=1.0, confidence=1.0)]})
    diagnosis.rerank(session_id, take_id)

    after = diagnosis.get(session_id, take_id)
    assert [(p["id"], p["kind"]) for p in after["problems"]] == [("p:t1:0", "form"), ("p:t1:1", "notes")]
    assert [s["problem_id"] for s in after["tier1"]] == ["p:t1:0", "p:t1:1"]
    assert after["notes"] == before["notes"] and after["bars"] == before["bars"]
    assert "p:t1:1" in (store.session_dir(session_id) / "t1_diagnosis.json").read_text()


def test_rerank_before_diagnosis_does_nothing(sessions_root):
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, perfect_played(SCALE_MIDIS))

    diagnosis.rerank(session_id, take_id)

    assert "diagnosis" not in get_take(session_id, take_id)


def test_rerank_on_a_cant_tell_take_does_nothing(sessions_root):
    session_id = make_session(make_score([[60, 62]]))
    take_id = add_transcribed_take(session_id, perfect_played([60, 62]), bar_to=1)
    diagnosis.run(session_id, take_id)
    before = get_take(session_id, take_id)["diagnosis"]
    assert (before["cant_tell"], before["cant_tell_reason"], before["problems"], before["tier1"]) == (
        True, "too_short", [], [],
    )

    update_take(session_id, take_id, form={"status": "ok", "flags": [flag()]})
    diagnosis.rerank(session_id, take_id)

    assert get_take(session_id, take_id)["diagnosis"] == before
    assert get_take(session_id, take_id)["form"]["flags"] == [flag()]
