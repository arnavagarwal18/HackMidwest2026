import pytest

from app import store
from app.practice import find_exercise, init_plan
from tests.practice_helpers import add_take, clean_diagnosis, diagnosis, exercise, save_plan


@pytest.fixture
def session_id(sessions_root):
    return store.create("trumpet").session_id


def progress(session_id):
    return store.get(session_id).progress


def test_creates_a_state_per_exercise(session_id):
    add_take(session_id, "t1")
    save_plan(session_id, "pl1", exercise("ex1", 2, 3, start_bpm=60), exercise("ex2", 1, 4, start_bpm=70))
    init_plan(session_id, "pl1")
    assert progress(session_id)["exercises"]["ex1"] == {
        "plan_id": "pl1", "current_bpm": 60, "streak": 0, "fails_in_row": 0, "best_passed_bpm": None,
        "complete": False, "rep_ids": [], "added_by": "plan"}
    assert progress(session_id)["exercises"]["ex2"]["current_bpm"] == 70


def test_before_take_is_the_first_diagnosed_take_and_never_a_cant_tell_take(session_id):
    add_take(session_id, "t1", diagnosis=diagnosis(cant_tell=True))
    add_take(session_id, "t2", purpose="rep")
    add_take(session_id, "t3", diagnosis=None, status="failed")
    add_take(session_id, "t4")
    save_plan(session_id, "pl1", exercise("ex1", 1, 4))
    init_plan(session_id, "pl1")
    assert progress(session_id)["before_take"] == "t4"


def test_put_it_together_is_added_last_when_no_exercise_has_the_before_bars(session_id):
    add_take(session_id, "t1", bar_from=1, bar_to=4, tempo_bpm=90.0)
    save_plan(session_id, "pl1", exercise("ex1", 2, 3, start_bpm=64), exercise("ex2", 3, 4, start_bpm=60))
    init_plan(session_id, "pl1")
    state = progress(session_id)
    assert list(state["exercises"]) == ["ex1", "ex2", "pl1:whole"]
    assert state["exercises"]["pl1:whole"]["added_by"] == "practice"
    assert state["exercises"]["pl1:whole"]["current_bpm"] == 60
    whole = find_exercise(session_id, "pl1:whole")
    assert (whole["bar_from"], whole["bar_to"], whole["start_bpm"], whole["target_bpm"]) == (1, 4, 60, 90.0)
    assert (whole["step_bpm"], whole["reps_to_pass"]) == (4, 1)
    assert whole["pass_mark"] == {"max_errors": 1, "max_mean_timing_ms": None, "form_rule": None}


def test_put_it_together_is_not_added_when_an_exercise_has_exactly_the_before_bars(session_id):
    add_take(session_id, "t1", bar_from=1, bar_to=4)
    save_plan(session_id, "pl1", exercise("ex1", 2, 3), exercise("ex2", 1, 4))
    init_plan(session_id, "pl1")
    assert list(progress(session_id)["exercises"]) == ["ex1", "ex2"]
    assert find_exercise(session_id, "pl1:whole") is None


def test_find_exercise_returns_a_plan_exercise(session_id):
    save_plan(session_id, "pl1", exercise("ex1"))
    assert find_exercise(session_id, "ex1")["id"] == "ex1"
    assert find_exercise(session_id, "nope") is None


def test_a_second_plan_adds_states_and_leaves_old_ones_untouched(session_id):
    add_take(session_id, "t1", bar_from=1, bar_to=4)
    save_plan(session_id, "pl1", exercise("ex1", 2, 3, start_bpm=60))
    init_plan(session_id, "pl1")
    old = {**progress(session_id)["exercises"]["ex1"], "current_bpm": 68, "streak": 1}
    store.update(session_id, "progress", {**progress(session_id), "exercises": {**progress(session_id)["exercises"], "ex1": old}})
    add_take(session_id, "t2", diagnosis=clean_diagnosis())
    save_plan(session_id, "pl2", exercise("ex1", 2, 3, start_bpm=60), exercise("ex2", 1, 2, start_bpm=50))
    init_plan(session_id, "pl2")
    state = progress(session_id)
    assert state["exercises"]["ex1"] == old
    assert state["exercises"]["ex2"]["plan_id"] == "pl2"
    assert list(state["exercises"]) == ["ex1", "pl1:whole", "ex2"]
    assert state["before_take"] == "t1"


def test_a_plan_before_any_usable_take_leaves_before_take_for_the_next_plan(session_id):
    add_take(session_id, "t1", diagnosis=diagnosis(cant_tell=True))
    save_plan(session_id, "pl1", exercise("ex1", 1, 4))
    init_plan(session_id, "pl1")
    assert progress(session_id)["before_take"] is None
    add_take(session_id, "t2", bar_from=2, bar_to=3)
    save_plan(session_id, "pl2", exercise("ex2", 1, 4))
    init_plan(session_id, "pl2")
    assert progress(session_id)["before_take"] == "t2"
    assert "pl2:whole" in progress(session_id)["exercises"]


def test_init_plan_for_an_unknown_plan_raises(session_id):
    with pytest.raises(KeyError):
        init_plan(session_id, "pl9")


def test_other_progress_keys_are_preserved(session_id):
    store.update(session_id, "progress", {"other": 1})
    save_plan(session_id, "pl1", exercise("ex1"))
    init_plan(session_id, "pl1")
    assert progress(session_id)["other"] == 1
