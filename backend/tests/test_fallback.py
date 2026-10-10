import json

import pytest

from app import store
from app.agents import run
from app.agents.checker import check_plan
from app.agents.context import build_context
from app.agents.fallback import CANT_TELL_TEXT, build_fallback
from tests.feedback_helpers import add_diagnosed_take

PLAN_KEYS = {"id", "take_id", "feedback_id", "mode", "exercises"}
FEEDBACK_KEYS = {"id", "take_id", "created_at", "mode", "fallback_reason", "cant_tell", "tier1", "sentences",
                 "dropped", "plan_id", "check", "duration_ms"}
TAKE = {"take_id": "t1", "bar_from": 1, "bar_to": 4}


@pytest.fixture(autouse=True)
def ai_off(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: False)


def saved(session_id, feedback_id):
    session = store.get(session_id)
    feedback = session.feedback[feedback_id]
    return feedback, session.plans[feedback["plan_id"]]


def plan_check(fixture_data, session_id, plan):
    ctx = build_context(session_id, plan["take_id"], lambda s, t: fixture_data["diagnosis"],
                        get_form=lambda s, t: fixture_data["form"], get_earlier_takes=lambda s, t: fixture_data["history"])
    return check_plan({"exercises": plan["exercises"]}, ctx)


def test_disabled_ai_gives_tier1_sentences_and_a_rule_plan(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback, plan = saved(session_id, run.run_feedback(session_id, take_id))
    assert set(feedback) == FEEDBACK_KEYS and set(plan) == PLAN_KEYS
    assert (feedback["id"], feedback["mode"], feedback["fallback_reason"], feedback["cant_tell"]) == ("fb1", "fallback", "disabled", False)
    assert feedback["tier1"] == fixture_data["diagnosis"]["tier1"]
    assert [s["text"] for s in feedback["sentences"]] == [t["text"] for t in fixture_data["diagnosis"]["tier1"]]
    assert all(s["checked"] and s["mode"] == "fallback" and s["cites"] for s in feedback["sentences"])
    assert feedback["sentences"][0]["jump"] == {"bar": 2, "time_s": None}
    assert feedback["check"] == {"coach_tries": 0, "planner_tries": 0, "claims_checked": 0, "claims_failed": 0, "sentences_dropped": 0}
    assert (plan["id"], plan["feedback_id"], plan["take_id"], plan["mode"]) == ("pl1", "fb1", "t1", "fallback")
    assert [e["id"] for e in plan["exercises"]] == ["ex1", "ex2", "ex3"]


def test_rule_plan_has_one_exercise_per_tier1_problem_plus_a_whole_range_one(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    _, plan = saved(session_id, run.run_feedback(session_id, take_id))
    notes, late, whole = plan["exercises"]
    assert (notes["bar_from"], notes["bar_to"], notes["problem_ids"]) == (2, 4, ["p:t1:0"])
    assert (late["bar_from"], late["bar_to"], late["problem_ids"]) == (3, 3, ["p:t1:1"])
    assert (whole["bar_from"], whole["bar_to"], whole["target_bpm"]) == (1, 4, 80)
    for exercise in (notes, late, whole):
        assert (exercise["start_bpm"], exercise["step_bpm"], exercise["reps_to_pass"]) == (56, 4, 2)  # no clean take yet: 70% of 80
    assert notes["pass_mark"] == {"max_errors": 0, "max_mean_timing_ms": None, "form_rule": None}
    assert late["pass_mark"] == {"max_errors": 0, "max_mean_timing_ms": 50, "form_rule": None}
    assert whole["pass_mark"]["max_errors"] == 1


def test_rule_plan_passes_the_plan_checker(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    _, plan = saved(session_id, run.run_feedback(session_id, take_id))
    result = plan_check(fixture_data, session_id, plan)
    assert result["ok"], result["problems"]


def test_without_tier1_problems_the_plan_has_two_whole_range_exercises_and_passes_the_checker(sessions_root, fixture_data):
    problems = [{**p, "tier": 2} for p in fixture_data["diagnosis"]["problems"]]
    session_id, take_id = add_diagnosed_take(fixture_data, problems=problems, tier1=[])
    feedback, plan = saved(session_id, run.run_feedback(session_id, take_id))
    assert feedback["sentences"] == []
    clean_run, whole = plan["exercises"]
    assert (clean_run["pass_mark"]["max_errors"], whole["pass_mark"]["max_errors"]) == (0, 1)
    assert all((e["bar_from"], e["bar_to"], e["target_bpm"]) == (1, 4, 80) for e in plan["exercises"])
    ctx = build_context(session_id, take_id, lambda s, t: {**fixture_data["diagnosis"], "problems": problems},
                        get_form=lambda s, t: fixture_data["form"], get_earlier_takes=lambda s, t: [])
    assert check_plan({"exercises": plan["exercises"]}, ctx)["ok"]


def test_form_problem_gets_a_form_rule(fixture_data):
    form_problem = {"id": "p:t1:2", "kind": "form", "bars": [4], "first_time_s": 10.2, "measurement_ids": ["f:t1:0"],
                    "size": 1, "certainty": 0.7, "score": 0.5, "tier": 1, "numbers": {}}
    diagnosis = {**fixture_data["diagnosis"], "problems": [*fixture_data["diagnosis"]["problems"], form_problem]}
    result = build_fallback(diagnosis, TAKE, [], {"f:t1:0": fixture_data["form"]["flags"][0]})
    assert [e["pass_mark"]["form_rule"] for e in result.exercises] == [None, None, "elbow_height", None]
    assert result.exercises[2]["pass_mark"]["max_mean_timing_ms"] is None


def test_at_most_three_problem_exercises_from_the_highest_scores(fixture_data):
    problems = [{"id": f"p:t1:{k}", "kind": "notes", "bars": [k + 1], "measurement_ids": [], "tier": 1, "score": k / 10, "numbers": {}}
                for k in range(5)]
    result = build_fallback({**fixture_data["diagnosis"], "problems": problems, "tier1": []}, TAKE, [], {})
    assert [e["problem_ids"] for e in result.exercises] == [["p:t1:4"], ["p:t1:3"], ["p:t1:2"], ["p:t1:4", "p:t1:3", "p:t1:2"]]


def test_start_is_70_percent_of_target_without_a_clean_take(fixture_data):
    result = build_fallback(fixture_data["diagnosis"], TAKE, [], {})
    assert {e["start_bpm"] for e in result.exercises} == {56}


def test_start_is_the_clean_tempo_when_an_earlier_take_was_clean(fixture_data):
    result = build_fallback(fixture_data["diagnosis"], TAKE, fixture_data["history"], {})
    assert {e["start_bpm"] for e in result.exercises} == {60}


def test_earlier_clean_take_on_the_same_bars_sets_the_start_in_a_real_run(sessions_root, fixture_data):
    session_id, _ = add_diagnosed_take(fixture_data)
    clean = {**fixture_data["diagnosis"], "error_rate": 0.0, "played_bpm": 64}
    take = store.get(session_id).takes["t1"]
    store.update(session_id, "takes", {"t1": {**take, "diagnosis": clean}, "t2": {**take, "take_id": "t2", "diagnosis": fixture_data["diagnosis"]}})
    _, plan = saved(session_id, run.run_feedback(session_id, "t2"))
    assert {e["start_bpm"] for e in plan["exercises"]} == {64}


def test_cant_tell_take_gives_the_message_and_one_retake_exercise(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data, cant_tell=True, cant_tell_reason="low_match", tier1=[])
    feedback, plan = saved(session_id, run.run_feedback(session_id, take_id))
    assert (feedback["fallback_reason"], feedback["cant_tell"], feedback["mode"]) == ("cant_tell", True, "fallback")
    assert [s["text"] for s in feedback["sentences"]] == [CANT_TELL_TEXT]
    [exercise] = plan["exercises"]
    assert (exercise["start_bpm"], exercise["target_bpm"], exercise["bar_from"], exercise["bar_to"]) == (56, 80, 1, 4)
    assert exercise["pass_mark"]["max_errors"] == 1


def test_enabled_ai_without_an_orchestrator_falls_back_with_model_error(sessions_root, fixture_data, monkeypatch, caplog):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback, _ = saved(session_id, run.run_feedback(session_id, take_id))
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "model_error")
    assert "Orchestrator isn't built yet" in caplog.text


def test_unreadable_ai_settings_fall_back_with_model_error(sessions_root, fixture_data, monkeypatch):
    def broken():
        raise RuntimeError("bad settings")

    monkeypatch.setattr(run, "ai_enabled", broken)
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback, _ = saved(session_id, run.run_feedback(session_id, take_id))
    assert feedback["fallback_reason"] == "model_error"


def test_a_failing_rule_plan_still_saves_a_whole_range_plan(sessions_root, fixture_data, monkeypatch, caplog):
    real = run.build_fallback

    def flaky(diagnosis, take, history, flags):
        if diagnosis:
            raise RuntimeError("rule bug")
        return real(diagnosis, take, history, flags)

    monkeypatch.setattr(run, "build_fallback", flaky)
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback, plan = saved(session_id, run.run_feedback(session_id, take_id))
    assert feedback["fallback_reason"] == "model_error" and len(plan["exercises"]) == 2
    assert "rule bug" in caplog.text


def test_a_take_without_diagnosis_still_gets_a_whole_range_plan(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    take = store.get(session_id).takes[take_id]
    store.update(session_id, "takes", {take_id: {k: v for k, v in take.items() if k != "diagnosis"}})
    feedback, plan = saved(session_id, run.run_feedback(session_id, take_id))
    assert feedback["sentences"] == [] and len(plan["exercises"]) == 2
    assert (plan["exercises"][0]["bar_from"], plan["exercises"][0]["bar_to"]) == (1, 4)


def test_ids_keep_counting_across_runs(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    run.run_feedback(session_id, take_id)
    feedback, plan = saved(session_id, run.run_feedback(session_id, take_id))
    assert (feedback["id"], plan["id"], plan["exercises"][0]["id"]) == ("fb2", "pl2", "ex4")


def test_the_trace_file_records_the_fallback(sessions_root, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback_id = run.run_feedback(session_id, take_id)
    events = json.loads((store.session_dir(session_id) / f"{feedback_id}_trace.json").read_text())
    assert [(e["agent"], e["event"], e["name"]) for e in events] == [("orchestrator", "fallback", "disabled")]
    assert set(events[0]) == {"t_ms", "agent", "event", "name", "detail", "duration_ms"}


def test_a_failing_trace_write_keeps_the_feedback(sessions_root, fixture_data, monkeypatch):
    monkeypatch.setattr(run.Trace, "save", lambda self, path: False)
    session_id, take_id = add_diagnosed_take(fixture_data)
    assert run.run_feedback(session_id, take_id) in store.get(session_id).feedback


def test_trace_save_reports_an_unwritable_path(tmp_path, caplog):
    trace = run.Trace()
    trace.add("coach", "tool", "get_bar", "x" * 900)
    assert trace.events[0]["detail"] == "x" * 500
    assert trace.save(tmp_path / "missing-folder" / "fb1_trace.json") is False
    assert "Could not write the trace" in caplog.text


def test_unsavable_feedback_fails_the_take_with_storage_error(sessions_root, fixture_data, monkeypatch, caplog):
    session_id, take_id = add_diagnosed_take(fixture_data)
    real_update = store.update

    def failing_update(sid, key, value):
        if key in ("feedback", "plans"):
            raise OSError("disk full")
        return real_update(sid, key, value)

    monkeypatch.setattr(store, "update", failing_update)
    assert run.run_feedback(session_id, take_id) is None
    take = store.get(session_id).takes[take_id]
    assert (take["status"], take["error"]) == ("failed", "storage_error")
    assert "could not be saved" in caplog.text


def test_practice_init_plan_is_called_when_it_exists_and_its_failure_is_survived(sessions_root, fixture_data, monkeypatch):
    calls = []

    def init_plan(session_id, plan_id):
        calls.append(plan_id)
        raise RuntimeError("practice broke")

    monkeypatch.setattr(run, "resolve_step", lambda module, attr: init_plan if (module, attr) == ("app.practice", "init_plan") else None)
    session_id, take_id = add_diagnosed_take(fixture_data)
    assert run.run_feedback(session_id, take_id) == "fb1"
    assert calls == ["pl1"]
