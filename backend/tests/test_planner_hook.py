from app.agents.checker import check_plan
from tests.planner_helpers import BAR_3, TOO_FAST, WHOLE_RANGE, run_planner, submit_plan
from tests.test_coach_hook import verdicts

# With the fixture's history the clean tempo is 60 BPM, so a start above 62 is too fast.
CLEAN_BAR_3 = {**BAR_3, "start_bpm": 58, "text": BAR_3["text"].replace("50", "58")}
CLEAN_WHOLE = {**WHOLE_RANGE, "start_bpm": 60, "text": WHOLE_RANGE["text"].replace("56", "60")}


def test_a_valid_plan_is_accepted_and_stored(fixture_data, check_ctx):
    agent, model, holder, trace = run_planner(fixture_data, check_ctx, [submit_plan(CLEAN_BAR_3, CLEAN_WHOLE)])
    assert verdicts(agent) == [{"accepted": True}]
    assert holder.plan == {"exercises": [CLEAN_BAR_3, CLEAN_WHOLE]}
    assert (holder.planner_tries, holder.plan_dropped, model.calls) == (1, [], 1)  # the agent stopped without another model turn
    assert [(e["agent"], e["event"], e["name"]) for e in trace.events] == [("checker", "check_pass", "submit_plan")]


def test_a_start_too_fast_is_rejected_with_the_reason_then_the_fixed_plan_is_accepted(fixture_data, check_ctx):
    agent, _, holder, _ = run_planner(fixture_data, check_ctx, [submit_plan(TOO_FAST, CLEAN_WHOLE), submit_plan(CLEAN_BAR_3, CLEAN_WHOLE)])
    first, second = verdicts(agent)
    assert (first["accepted"], first["try"]) == (False, 1)
    [problem] = first["problems"]
    assert problem["exercise"] == 0 and problem["reason"].startswith("start too fast")
    assert second == {"accepted": True}
    assert (holder.planner_tries, holder.plan["exercises"][0]["start_bpm"]) == (2, 58)
    assert holder.check_counts()["planner_tries"] == 2


def test_the_same_bad_exercise_twice_is_dropped_and_the_rest_kept(fixture_data, check_ctx):
    plan = submit_plan(TOO_FAST, CLEAN_BAR_3, CLEAN_WHOLE)
    agent, _, holder, _ = run_planner(fixture_data, check_ctx, [plan, plan])
    assert verdicts(agent)[1] == {"accepted": True, "dropped": 1}
    assert holder.plan["exercises"] == [CLEAN_BAR_3, CLEAN_WHOLE]
    [dropped] = holder.plan_dropped
    assert dropped["text"] == TOO_FAST["text"] and dropped["reasons"][0].startswith("start too fast")
    assert check_plan(holder.plan, check_ctx)["ok"]


def test_fewer_than_two_exercises_left_after_dropping_is_refused_and_nothing_is_stored(fixture_data, check_ctx):
    plan = submit_plan(TOO_FAST, CLEAN_WHOLE)
    agent, _, holder, trace = run_planner(fixture_data, check_ctx, [plan, plan])
    final = verdicts(agent)[1]
    assert (final["accepted"], final["final"]) == (False, True)
    assert (holder.plan, holder.plan_dropped, holder.planner_tries) == (None, [], 2)
    assert trace.events[-1]["event"] == "check_fail"


def test_a_malformed_plan_is_refused_with_the_schema_error(fixture_data, check_ctx):
    broken = {k: v for k, v in CLEAN_BAR_3.items() if k != "start_bpm"}
    agent, _, holder, _ = run_planner(fixture_data, check_ctx, [submit_plan(broken, CLEAN_WHOLE), submit_plan(CLEAN_BAR_3, CLEAN_WHOLE)])
    first, second = verdicts(agent)
    assert first["problems"][0]["reason"].startswith("bad submission") and second == {"accepted": True}
    assert holder.planner_tries == 2
