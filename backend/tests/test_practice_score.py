import logging

import pytest

from app import store
from app.practice import init_plan, score_rep, scoring
from tests.practice_helpers import add_rep, add_take, bad_diagnosis, diagnosis, exercise, note, save_plan


@pytest.fixture
def session_id(sessions_root):
    sid = store.create("trumpet").session_id
    add_take(sid, "t0", bar_from=2, bar_to=3)
    save_plan(sid, "pl1", exercise("ex1", 2, 3, start_bpm=60, target_bpm=72, step_bpm=4, reps_to_pass=2))
    init_plan(sid, "pl1")
    return sid


def state(sid):
    return store.get(sid).progress["exercises"]["ex1"]


def rep(sid, take_id):
    return store.get(sid).progress["reps"][take_id]


def set_state(sid, **changes):
    progress = store.get(sid).progress
    store.update(sid, "progress", {**progress, "exercises": {"ex1": {**state(sid), **changes}}})


def set_mark(sid, **pass_mark):
    save_plan(sid, "pl1", exercise("ex1", 2, 3, start_bpm=60, target_bpm=72, step_bpm=4, reps_to_pass=2, **pass_mark))


def test_passing_rep_is_scored_and_extends_the_streak(session_id):
    add_rep(session_id, "t1")
    score_rep(session_id, "t1")
    assert rep(session_id, "t1") == {
        "take_id": "t1", "exercise_id": "ex1", "tempo_bpm": 60.0, "status": "scored", "passed": True, "reasons": [],
        "errors": 0, "mean_abs_timing_ms": 0.0, "form_flag_ids": [], "next_bpm": 60, "streak": 1, "exercise_complete": False}
    assert state(session_id)["streak"] == 1 and state(session_id)["best_passed_bpm"] == 60
    assert state(session_id)["rep_ids"] == ["t1"]


def test_failing_rep_gives_the_reason_with_number_and_pass_mark(session_id):
    add_rep(session_id, "t1", diag=bad_diagnosis())
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["passed"] is False
    assert rep(session_id, "t1")["reasons"] == ["1 error, pass mark 0"]
    assert state(session_id)["fails_in_row"] == 1


def test_timing_mark_failure_reason(session_id):
    set_mark(session_id, max_mean_timing_ms=50)
    add_rep(session_id, "t1", diag=diagnosis(note(2, timing_ms=80), note(3, timing_ms=100)))
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["reasons"] == ["mean timing 90 ms, pass mark 50 ms"]


def test_form_flag_fails_a_done_video_rep(session_id):
    set_mark(session_id, form_rule="elbow")
    flag = {"id": "f1", "rule": "elbow", "label": "Elbow up", "start_s": 65}
    add_rep(session_id, "t1", kind="video", form_status="done", form={"flags": [flag]})
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["passed"] is False
    assert rep(session_id, "t1")["form_flag_ids"] == ["f1"]
    assert rep(session_id, "t1")["reasons"] == ["Elbow up at 1:05"]


def test_form_rule_on_a_mic_rep_is_judged_on_notes_with_form_not_checked(session_id):
    set_mark(session_id, form_rule="elbow")
    add_rep(session_id, "t1")
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["status"] == "scored" and rep(session_id, "t1")["passed"] is True
    assert rep(session_id, "t1")["reasons"] == ["form not checked"]


def test_form_rule_on_a_video_whose_form_failed_is_form_not_checked(session_id):
    set_mark(session_id, form_rule="elbow")
    add_rep(session_id, "t1", kind="video", form_status="failed")
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["reasons"] == ["form not checked"]


def test_cant_tell_is_not_counted_and_leaves_the_ladder(session_id):
    before = dict(state(session_id))
    add_rep(session_id, "t1", diag=diagnosis(cant_tell=True))
    score_rep(session_id, "t1")
    result = rep(session_id, "t1")
    assert (result["status"], result["passed"]) == ("not_counted", None)
    assert result["reasons"] == ["could not line up this rep with bars 2-3"]
    assert state(session_id) == before


def test_failed_take_is_failed_with_its_error_and_leaves_the_ladder(session_id):
    before = dict(state(session_id))
    add_rep(session_id, "t1", status="failed", error="no_notes_heard")
    store.get(session_id).takes["t1"]["diagnosis"] = None
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["status"] == "failed"
    assert rep(session_id, "t1")["reasons"] == ["no_notes_heard"]
    assert state(session_id) == before


def test_an_unexpected_exception_is_logged_and_gives_scoring_failed(session_id, monkeypatch, caplog):
    before = dict(state(session_id))
    add_rep(session_id, "t1")

    def boom(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(scoring, "judge_rep", boom)
    with caplog.at_level(logging.ERROR, logger="app.practice"):
        score_rep(session_id, "t1")
    assert rep(session_id, "t1")["status"] == "failed" and rep(session_id, "t1")["reasons"] == ["scoring failed"]
    assert state(session_id) == before
    assert "t1" in caplog.text


def test_a_rep_for_an_unknown_exercise_is_scoring_failed(session_id):
    add_rep(session_id, "t1", exercise_id="nope")
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["reasons"] == ["scoring failed"]


def test_a_rep_without_a_diagnosis_is_scoring_failed(session_id):
    add_rep(session_id, "t1")
    store.get(session_id).takes["t1"]["diagnosis"] = None
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["reasons"] == ["scoring failed"]


def test_score_rep_never_raises_even_when_the_session_is_gone(sessions_root):
    score_rep("missing", "t1")


def test_scoring_a_rep_twice_does_not_step_the_ladder_twice(session_id):
    add_rep(session_id, "t1")
    score_rep(session_id, "t1")
    score_rep(session_id, "t1")
    assert state(session_id)["streak"] == 1


def test_two_passes_step_up_to_64(session_id):
    add_rep(session_id, "t1")
    add_rep(session_id, "t2")
    score_rep(session_id, "t1")
    score_rep(session_id, "t2")
    assert rep(session_id, "t2")["next_bpm"] == 64
    assert (state(session_id)["current_bpm"], state(session_id)["streak"]) == (64, 0)


def test_two_fails_at_64_step_down_to_60(session_id):
    set_state(session_id, current_bpm=64)
    add_rep(session_id, "t1", tempo_bpm=64.0, diag=bad_diagnosis())
    add_rep(session_id, "t2", tempo_bpm=64.0, diag=bad_diagnosis())
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["next_bpm"] == 64
    score_rep(session_id, "t2")
    assert rep(session_id, "t2")["next_bpm"] == 60
    assert state(session_id)["fails_in_row"] == 0


def test_passing_at_the_target_completes_the_exercise(session_id):
    set_state(session_id, current_bpm=72, streak=1)
    add_rep(session_id, "t1", tempo_bpm=72.0)
    score_rep(session_id, "t1")
    assert rep(session_id, "t1")["exercise_complete"] is True
    assert state(session_id)["best_passed_bpm"] == 72
