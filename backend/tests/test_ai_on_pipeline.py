"""run_take_pipeline with AI on: a take's feedback comes from the (faked) Orchestrator, Coach and Planner, and the
saved plan feeds practice init_plan and score_rep. The model is stubbed, so nothing here calls Bedrock."""
import pytest

from app import store
from app.agents import ai_run, run
from app.practice import init_plan, score_rep
from app.takes import pipeline
from app.takes.take_store import add_take, update_take
from app.takes.validation import TakeRequest, new_take_fields
from tests.media_factory import make_wav
from tests.planner_helpers import BAR_3, submit_plan
from tests.practice_helpers import add_rep, diagnosis, note
from tests.test_checker_feedback import LATE_TEXT, sentence
from tests.test_coach_hook import submit
from tests.test_pipeline import NOTE
from tests.test_run_planner import ACCESS_DENIED, BOTH_TOOLS, use_agents

HEAD_DOWN = "trumpet_head_down"
# Neither exercise covers the take's bars 1-4, so practice init_plan adds "{plan_id}:whole" after them.
BARS_2_TO_4 = {
    **BAR_3, "title": "Bars 2 to 4", "bar_from": 2, "bar_to": 4, "start_bpm": 56, "target_bpm": 80, "step_bpm": 5, "reps_to_pass": 2,
    "text": "Play bars 2 to 4 from 56 BPM to 80 BPM in steps of 5, 2 clean reps.",
    "pass_mark": {"max_errors": 1, "max_mean_timing_ms": None, "form_rule": None}, "problem_ids": ["p:t1:0"],
}
HEAD_DOWN_BAR_4 = {
    **BAR_3, "title": "Keep the head up", "bar_from": 4, "bar_to": 4,
    "text": "Play bar 4 at 50 BPM, up 4 BPM per step to 70 BPM, 3 clean reps.",
    "pass_mark": {"max_errors": 0, "max_mean_timing_ms": None, "form_rule": HEAD_DOWN}, "problem_ids": ["p:t1:2"],
}


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)


@pytest.fixture
def session_id(sessions_root):
    return store.create("trumpet").session_id


def add_pipeline_take(session_id, tmp_path) -> str:
    """A recorded mic take of bars 1-4 at 80 BPM (the fixture diagnosis's target) with a real wav for audio extraction."""
    request = TakeRequest(kind="mic", source="recorded", bar_from=1, bar_to=4, tempo_bpm=80, count_in_beats=4, downbeat_s=0.5)
    wav = make_wav(tmp_path / "a.wav")
    take = add_take(session_id, lambda take_id: new_take_fields(take_id, request, f"{take_id}_upload.wav"),
                    lambda take: (store.session_dir(session_id) / take["file"]).write_bytes(wav.read_bytes()))
    return take["take_id"]


def run_pipeline(session_id, tmp_path, fixture_data) -> str:
    """Run the whole pipeline for a new take, with the transcriber and diagnosis stubbed and the real feedback and practice steps."""
    take_id = add_pipeline_take(session_id, tmp_path)

    def diagnose(session_id, take_id):
        update_take(session_id, take_id, diagnosis=fixture_data["diagnosis"], form=fixture_data["form"])

    pipeline.run_take_pipeline(session_id, take_id, transcriber=lambda *args: [NOTE], diagnose=diagnose)
    return take_id


def progress_of(session_id) -> dict:
    return store.get(session_id).progress


def ai_script(*plan_exercises, runs=1):
    """Orchestrator, Coach and Planner scripts for `runs` feedback runs that each ask for both agents."""
    return dict(orchestrator=BOTH_TOOLS * runs, coach=[submit(sentence())] * runs, planner=[submit_plan(*plan_exercises)] * runs)


def test_a_take_with_ai_on_gets_ai_feedback_a_saved_plan_and_practice_state(session_id, tmp_path, fixture_data, monkeypatch):
    use_agents(monkeypatch, **ai_script(BAR_3, BARS_2_TO_4))
    take_id = run_pipeline(session_id, tmp_path, fixture_data)

    session = store.get(session_id)
    assert (session.takes[take_id]["status"], session.takes[take_id]["error"]) == ("done", None)
    [feedback] = session.feedback.values()
    assert (feedback["mode"], feedback["fallback_reason"], feedback["take_id"]) == ("ai", None, take_id)
    assert [s["text"] for s in feedback["sentences"]] == [LATE_TEXT]
    plan = session.plans[feedback["plan_id"]]
    assert (plan["mode"], [e["id"] for e in plan["exercises"]]) == ("ai", ["ex1", "ex2"])
    assert plan["exercises"][0]["title"] == BAR_3["title"]

    progress = progress_of(session_id)
    assert set(progress["exercises"]) == {"ex1", "ex2", f"{plan['id']}:whole"}
    assert [progress["exercises"][e]["plan_id"] for e in ("ex1", "ex2")] == [plan["id"]] * 2
    assert progress["exercises"]["ex1"]["current_bpm"] == BAR_3["start_bpm"]
    whole = progress["added_exercises"][f"{plan['id']}:whole"]
    assert (whole["bar_from"], whole["bar_to"]) == (1, 4) and progress["exercises"][whole["id"]]["added_by"] == "practice"
    assert progress["before_take"] == take_id


@pytest.mark.parametrize("flags, passed, reasons", [
    ([], True, []),
    ([{"id": "f:t2:0", "rule": HEAD_DOWN, "label": "Head drops", "start_s": 9.5}], False, ["Head drops at 0:09"]),
    ([{"id": "f:t2:0", "rule": "elbow_height", "label": "Elbow drops", "start_s": 4.0}], True, []),
], ids=["no_flag", "flag_of_the_rule", "flag_of_another_rule"])
def test_an_ai_planned_form_rule_exercise_is_scored_on_the_form_rule(session_id, tmp_path, fixture_data, monkeypatch, flags, passed, reasons):
    use_agents(monkeypatch, **ai_script(HEAD_DOWN_BAR_4, BAR_3))
    run_pipeline(session_id, tmp_path, fixture_data)
    assert progress_of(session_id)["exercises"]["ex1"]["streak"] == 0

    add_rep(session_id, "t2", exercise_id="ex1", tempo_bpm=50.0, kind="video", form_status="done", form={"flags": flags},
            diag=diagnosis(note(4)))
    score_rep(session_id, "t2")

    progress = progress_of(session_id)
    rep, state = progress["reps"]["t2"], progress["exercises"]["ex1"]
    assert (rep["status"], rep["passed"], rep["errors"]) == ("scored", passed, 0)
    assert rep["reasons"] == reasons and rep["form_flag_ids"] == [f["id"] for f in flags if f["rule"] == HEAD_DOWN]
    assert (state["streak"], state["fails_in_row"], state["rep_ids"]) == ((1, 0, ["t2"]) if passed else (0, 1, ["t2"]))


def test_a_second_take_adds_a_second_plan_and_leaves_the_first_plans_states_alone(session_id, tmp_path, fixture_data, monkeypatch):
    use_agents(monkeypatch, **ai_script(BAR_3, BARS_2_TO_4, runs=2))
    first_take = run_pipeline(session_id, tmp_path, fixture_data)
    add_rep(session_id, "t2", exercise_id="ex1", tempo_bpm=50.0, diag=diagnosis(note(3)))
    score_rep(session_id, "t2")
    before = progress_of(session_id)
    assert before["exercises"]["ex1"]["streak"] == 1

    second_take = run_pipeline(session_id, tmp_path, fixture_data)

    session = store.get(session_id)
    assert (first_take, second_take) == ("t1", "t3")
    assert list(session.plans) == ["pl1", "pl2"] and list(session.feedback) == ["fb1", "fb2"]
    assert [(f["mode"], f["plan_id"]) for f in session.feedback.values()] == [("ai", "pl1"), ("ai", "pl2")]
    assert [e["id"] for e in session.plans["pl2"]["exercises"]] == ["ex3", "ex4"]
    after = progress_of(session_id)
    assert set(after["exercises"]) == {"ex1", "ex2", "pl1:whole", "ex3", "ex4"}
    for exercise_id in before["exercises"]:
        assert after["exercises"][exercise_id] == before["exercises"][exercise_id]
    assert [after["exercises"][e]["plan_id"] for e in ("ex3", "ex4")] == ["pl2", "pl2"]
    assert after["reps"] == before["reps"] and after["before_take"] == "t1"
    assert "pl2:whole" not in after["added_exercises"]


def test_init_plan_run_again_for_a_saved_ai_plan_changes_nothing(session_id, tmp_path, fixture_data, monkeypatch):
    use_agents(monkeypatch, **ai_script(BAR_3, BARS_2_TO_4))
    run_pipeline(session_id, tmp_path, fixture_data)
    before = progress_of(session_id)
    init_plan(session_id, "pl1")
    assert progress_of(session_id) == before


def test_a_model_that_raises_still_completes_the_take_with_fallback_feedback(session_id, tmp_path, fixture_data, monkeypatch):
    use_agents(monkeypatch, [ACCESS_DENIED])
    take_id = run_pipeline(session_id, tmp_path, fixture_data)

    session = store.get(session_id)
    assert (session.takes[take_id]["status"], session.takes[take_id]["error"]) == ("done", None)
    [feedback] = session.feedback.values()
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "model_error")
    assert feedback["sentences"] and all(s["mode"] == "fallback" for s in feedback["sentences"])
    plan = session.plans[feedback["plan_id"]]
    assert plan["mode"] == "fallback" and progress_of(session_id)["exercises"]  # the rule plan still gets practice state


def test_the_fake_model_is_what_the_pipeline_uses(session_id, tmp_path, fixture_data, monkeypatch):
    """Guards the setup: new_model is stubbed, so a run can't reach a real model."""
    model = use_agents(monkeypatch, **ai_script(BAR_3, BARS_2_TO_4))
    assert ai_run.new_model() is model
    run_pipeline(session_id, tmp_path, fixture_data)
    assert all(m.calls > 0 for m in model.by_prompt.values())
