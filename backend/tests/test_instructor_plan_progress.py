"""The Instructor's get_plan tool shows the learner's practice progress on the plan, read from session.progress as LLD-6 writes it."""
import json

import pytest

from app import store
from app.agents.instructor import make_chat_tools
from app.practice import init_plan, score_rep
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
