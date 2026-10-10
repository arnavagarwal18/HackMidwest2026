import time

import pytest
from botocore.exceptions import ClientError

from app import store
from app.agents import ai_run, run
from app.agents.fallback import CANT_TELL_TEXT
from app.agents.prompts import COACH_PROMPT, ORCHESTRATOR_PROMPT, PLANNER_PROMPT
from tests.fake_model import RoutedModel, slow, text_turn, tool_turn, tools_turn
from tests.feedback_helpers import add_diagnosed_take
from tests.planner_helpers import BAR_3, TOO_FAST, WHOLE_RANGE, submit_plan
from tests.test_checker_feedback import LATE_TEXT, sentence
from tests.test_coach_hook import submit

COACH_BRIEF = ("coach", {"brief": "Take t1, tier 1 problems p:t1:0 and p:t1:1, trumpet."})
PLANNER_BRIEF = ("planner", {"brief": "Take t1, tier 1 problems p:t1:0 and p:t1:1, trumpet."})
BOTH_TOOLS = [tool_turn("get_take_overview", {}), tools_turn(COACH_BRIEF, PLANNER_BRIEF), text_turn()]
ONLY_PLANNER = [tool_turn("get_take_overview", {}), tool_turn(*PLANNER_BRIEF), text_turn()]
ACCESS_DENIED = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "not allowed"}}, "ConverseStream")


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)


def use_agents(monkeypatch, orchestrator, coach=None, planner=None):
    scripts = {ORCHESTRATOR_PROMPT: orchestrator}
    if coach is not None:
        scripts[COACH_PROMPT] = coach
    if planner is not None:
        scripts[PLANNER_PROMPT] = planner
    model = RoutedModel(scripts)
    monkeypatch.setattr(ai_run, "new_model", lambda: model)
    return model


def feedback_of(fixture_data, **diagnosis_changes):
    session_id, take_id = add_diagnosed_take(fixture_data, **diagnosis_changes)
    feedback_id = run.run_feedback(session_id, take_id)
    session = store.get(session_id)
    feedback = session.feedback[feedback_id]
    return feedback, session.plans[feedback["plan_id"]]


def test_coach_and_planner_asked_for_in_one_reply_run_at_the_same_time(sessions_root, fixture_data, monkeypatch):
    model = use_agents(monkeypatch, BOTH_TOOLS, coach=[slow(submit(sentence()), 1)], planner=[slow(submit_plan(BAR_3, WHOLE_RANGE), 1)])
    started = time.monotonic()
    feedback, plan = feedback_of(fixture_data)
    elapsed = time.monotonic() - started
    coach_start, planner_start = (model.by_prompt[p].call_times[0] for p in (COACH_PROMPT, PLANNER_PROMPT))
    assert elapsed < 1.8, f"the two agents ran one after the other ({elapsed:.2f} s)"
    assert abs(coach_start - planner_start) < 0.5
    assert (feedback["mode"], feedback["fallback_reason"], plan["mode"]) == ("ai", None, "ai")
    assert [s["text"] for s in feedback["sentences"]] == [LATE_TEXT]
    assert (plan["id"], plan["take_id"], plan["feedback_id"], feedback["plan_id"]) == ("pl1", "t1", "fb1", "pl1")
    assert [e["id"] for e in plan["exercises"]] == ["ex1", "ex2"]
    assert plan["exercises"][0] == {"id": "ex1", **BAR_3}
    assert (feedback["check"]["coach_tries"], feedback["check"]["planner_tries"]) == (1, 1)


def test_a_rejected_first_plan_is_fixed_on_the_second_try(sessions_root, fixture_data, monkeypatch):
    use_agents(monkeypatch, BOTH_TOOLS, coach=[submit(sentence())], planner=[submit_plan(TOO_FAST, WHOLE_RANGE), submit_plan(BAR_3, WHOLE_RANGE)])
    feedback, plan = feedback_of(fixture_data)
    assert (plan["mode"], feedback["check"]["planner_tries"]) == ("ai", 2)
    assert plan["exercises"][0]["start_bpm"] == 50


def test_an_exercise_that_fails_twice_is_dropped_and_the_rest_kept(sessions_root, fixture_data, monkeypatch):
    bad_plan = submit_plan(TOO_FAST, BAR_3, WHOLE_RANGE)
    use_agents(monkeypatch, BOTH_TOOLS, coach=[submit(sentence())], planner=[bad_plan, bad_plan])
    feedback, plan = feedback_of(fixture_data)
    assert (plan["mode"], feedback["check"]["planner_tries"]) == ("ai", 2)
    assert [(e["id"], e["start_bpm"]) for e in plan["exercises"]] == [("ex1", 50), ("ex2", 56)]


def test_fewer_than_two_exercises_left_after_dropping_uses_the_rule_plan(sessions_root, fixture_data, monkeypatch):
    bad_plan = submit_plan(TOO_FAST, WHOLE_RANGE)
    use_agents(monkeypatch, BOTH_TOOLS, coach=[submit(sentence())], planner=[bad_plan, bad_plan])
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], plan["mode"], len(plan["exercises"])) == ("ai", "fallback", 3)
    assert feedback["check"]["planner_tries"] == 2


def test_a_planner_that_raises_keeps_the_coach_sentences_and_uses_the_rule_plan(sessions_root, fixture_data, monkeypatch, caplog):
    use_agents(monkeypatch, BOTH_TOOLS, coach=[submit(sentence())], planner=[ACCESS_DENIED])
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"], [s["text"] for s in feedback["sentences"]]) == ("ai", None, [LATE_TEXT])
    assert (plan["mode"], len(plan["exercises"]), plan["exercises"][0]["id"]) == ("fallback", 3, "ex1")
    assert "The planner failed" in caplog.text and "No Planner plan" in caplog.text


def test_a_planner_that_never_submits_uses_the_rule_plan(sessions_root, fixture_data, monkeypatch):
    use_agents(monkeypatch, BOTH_TOOLS, coach=[submit(sentence())], planner=[text_turn("I would rather not.")])
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], plan["mode"]) == ("ai", "fallback")


def test_a_failed_coach_keeps_the_planners_plan(sessions_root, fixture_data, monkeypatch):
    use_agents(monkeypatch, BOTH_TOOLS, coach=[ACCESS_DENIED], planner=[submit_plan(BAR_3, WHOLE_RANGE)])
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"], plan["mode"]) == ("fallback", "model_error", "ai")
    assert feedback["sentences"][0]["mode"] == "fallback"


def test_a_take_that_cant_be_judged_calls_only_the_planner_and_saves_its_plan(sessions_root, fixture_data, monkeypatch):
    model = use_agents(monkeypatch, ONLY_PLANNER, planner=[submit_plan(BAR_3, WHOLE_RANGE)])
    feedback, plan = feedback_of(fixture_data, cant_tell=True)
    assert COACH_PROMPT not in model.by_prompt and model.by_prompt[PLANNER_PROMPT].calls == 1
    assert (feedback["mode"], feedback["fallback_reason"], feedback["cant_tell"]) == ("fallback", "cant_tell", True)
    assert [s["text"] for s in feedback["sentences"]] == [CANT_TELL_TEXT]
    assert (plan["mode"], [e["id"] for e in plan["exercises"]], feedback["plan_id"]) == ("ai", ["ex1", "ex2"], plan["id"])
    assert feedback["check"]["planner_tries"] == 1


def test_a_cant_tell_take_whose_planner_fails_gets_one_whole_range_exercise_at_70_percent(sessions_root, fixture_data, monkeypatch):
    use_agents(monkeypatch, ONLY_PLANNER, planner=[ACCESS_DENIED])
    feedback, plan = feedback_of(fixture_data, cant_tell=True)
    assert (feedback["fallback_reason"], plan["mode"]) == ("cant_tell", "fallback")
    [exercise] = plan["exercises"]
    assert (exercise["bar_from"], exercise["bar_to"], exercise["start_bpm"], exercise["target_bpm"]) == (1, 4, 56, 80)
