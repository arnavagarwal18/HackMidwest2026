"""The Instructor's get_plan tool shows the learner's practice progress on the plan, read from session.progress as LLD-6 writes it."""
import json

import pytest

from app import store
from app.agents.instructor import make_chat_tools
from app.practice import init_plan, score_rep
from app.practice.progress import update_progress
from tests.practice_helpers import add_rep, add_take, exercise, save_plan

PLAN_ID = "pl1"


@pytest.fixture
def session_id(sessions_root):
    return store.create("trumpet").session_id


def get_plan(session_id, take_id="t1"):
    return json.loads(make_chat_tools(session_id, {"take_id": take_id, "bar_from": 1, "bar_to": 4})["get_plan"]())


def add_plan(session_id, plan_id, take_id, *exercises):
    save_plan(session_id, plan_id, *exercises)
    session = store.get(session_id)
    store.update(session_id, "plans", {**session.plans, plan_id: {**session.plans[plan_id], "take_id": take_id}})


@pytest.fixture
def practised(session_id):
    """Plan pl1 for take t1 with exercises ex1 (one clean rep scored) and ex2 (none), plus the added 'Put it together'."""
    add_take(session_id, "t1", bar_from=1, bar_to=8, tempo_bpm=70.0)
    add_plan(session_id, PLAN_ID, "t1", exercise("ex1", 2, 3, start_bpm=60), exercise("ex2", 4, 5, start_bpm=50))
    init_plan(session_id, PLAN_ID)
    add_rep(session_id, "r1", "ex1", 60.0)
    score_rep(session_id, "r1")
    return session_id


def test_the_plan_carries_progress_for_each_of_its_exercises(practised):
    progress = get_plan(practised)["progress"]
    assert set(progress["exercises"]) == {"ex1", "ex2", f"{PLAN_ID}:whole"}
    ex1, ex2 = progress["exercises"]["ex1"], progress["exercises"]["ex2"]
    assert (ex1["current_bpm"], ex1["streak"], ex1["reps"], ex1["passes"]) == (60, 1, 1, 1)
    assert ex1["rep_results"][0]["take_id"] == "r1"
    assert (ex2["current_bpm"], ex2["streak"], ex2["reps"], ex2["rep_results"]) == (50, 0, 0, [])


def test_the_plan_keeps_its_own_fields_next_to_progress(practised):
    plan = get_plan(practised)
    assert plan["id"] == PLAN_ID and [ex["id"] for ex in plan["exercises"]] == ["ex1", "ex2"]


def test_another_plans_exercises_are_left_out(practised):
    add_plan(practised, "pl2", "t2", exercise("ex9", 1, 2))
    init_plan(practised, "pl2")
    assert set(get_plan(practised)["progress"]["exercises"]) == {"ex1", "ex2", f"{PLAN_ID}:whole"}
    assert set(get_plan(practised, "t2")["progress"]["exercises"]) == {"ex9"}


def test_a_plan_with_no_progress_has_no_progress_key(session_id):
    add_take(session_id, "t1")
    add_plan(session_id, PLAN_ID, "t1", exercise("ex1"))
    plan = get_plan(session_id)
    assert plan["id"] == PLAN_ID and "progress" not in plan


def test_a_take_without_a_plan_gets_null(session_id):
    assert get_plan(session_id) is None


def test_progress_is_not_keyed_by_plan_id_so_the_plan_lookup_must_filter_exercise_states(practised):
    """849e730 read session.progress.get(plan_id), which is always empty: progress is keyed by section, not plan."""
    assert PLAN_ID not in store.get(practised).progress
    assert get_plan(practised)["progress"]["exercises"]


def test_reps_recorded_for_another_plan_do_not_count_for_this_one(practised):
    add_take(practised, "t2", bar_from=1, bar_to=8)
    add_plan(practised, "pl2", "t2", exercise("ex9", 1, 2, start_bpm=40))
    init_plan(practised, "pl2")
    add_rep(practised, "r2", "ex9", 40.0)
    score_rep(practised, "r2")
    mine, other = get_plan(practised)["progress"]["exercises"], get_plan(practised, "t2")["progress"]["exercises"]
    assert [rep["take_id"] for ex in mine.values() for rep in ex["rep_results"]] == ["r1"]
    assert [rep["take_id"] for rep in other["ex9"]["rep_results"]] == ["r2"]


def test_a_rep_id_with_no_saved_rep_is_skipped(practised):
    def lose_the_rep(progress):
        progress["reps"].pop("r1")

    update_progress(practised, lose_the_rep)
    ex1 = get_plan(practised)["progress"]["exercises"]["ex1"]
    assert (ex1["reps"], ex1["passes"], ex1["rep_results"]) == (0, 0, [])


def test_the_last_five_reps_are_shown(practised):
    for number in range(2, 9):
        add_rep(practised, f"r{number}", "ex1", 60.0)
        score_rep(practised, f"r{number}")
    results = get_plan(practised)["progress"]["exercises"]["ex1"]["rep_results"]
    assert [rep["take_id"] for rep in results] == ["r4", "r5", "r6", "r7", "r8"]


def test_an_exercise_state_with_no_definition_is_left_out_and_logged(practised, caplog):
    update_progress(practised, lambda progress: progress["exercises"].update(ghost={**progress["exercises"]["ex1"]}))
    exercises = get_plan(practised)["progress"]["exercises"]
    assert "ghost" not in exercises and "ex1" in exercises
    assert "Exercise ghost" in caplog.text
