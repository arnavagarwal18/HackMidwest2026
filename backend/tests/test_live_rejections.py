"""What live Bedrock runs got rejected for (live_check, 2026-10-11) as fake model output, and what the agents now ask for instead."""
from app.agents import live_check
from app.agents.checker import check_plan
from app.agents.coach import Claim, CoachSentence
from app.agents.holder import describe_rejections
from app.agents.planner import PLANNER_TOOLS
from app.agents.prompts import COACH_PROMPT, PLANNER_PROMPT
from tests.fake_model import text_turn, tool_turn, tools_turn
from tests.planner_helpers import BAR_3, WHOLE_RANGE, run_planner, submit_plan
from tests.test_checker_feedback import claim, sentence
from tests.test_coach_hook import run_coach, submit, verdicts
from tests.test_live_check import BRIEF, settings_on, use_agents  # noqa: F401  (settings_on is the autouse fixture the live check tests need)

CLEAN_BAR_3 = {**BAR_3, "start_bpm": 58, "text": "Play bar 3 at 58 BPM, up 4 BPM per step to 70 BPM, 3 clean reps."}
CLEAN_WHOLE = {**WHOLE_RANGE, "start_bpm": 60, "text": "Play bars 1 to 4 from 60 BPM to 80 BPM in steps of 5, 2 clean reps."}
# As the live Planner wrote it: bars 2-3 leave out bar 4 of problem p:t1:0, the target overshoots the take's 80 BPM,
# the start is above the clean tempo, and the bar claims have no value.
LIVE_PLAN_BAD = {
    **WHOLE_RANGE, "bar_from": 2, "bar_to": 3, "start_bpm": 78, "target_bpm": 85, "step_bpm": 4,
    "text": "Play bars 2 to 3 from 78 BPM up to 85 BPM, 2 clean reps.",
    "claims": [claim("bar", "b:t1:2", None), claim("bar", "b:t1:3", None)],
}


def test_the_live_planner_rejections_are_each_reported_with_their_reason(check_ctx):
    result = check_plan({"exercises": [LIVE_PLAN_BAD, CLEAN_WHOLE]}, check_ctx)
    reasons = [p["reason"] for p in result["problems"]]
    for prefix in ("bars outside range", "bad tempo: target 85", "start too fast", "bad claim: value must be a number"):
        assert any(r.startswith(prefix) for r in reasons), (prefix, reasons)
    assert {p["index"] for p in result["problems"]} == {0}


def test_the_planner_is_accepted_once_it_covers_the_problem_bars_and_starts_at_the_clean_tempo(fixture_data, check_ctx):
    covering = {**CLEAN_BAR_3, "bar_from": 2, "bar_to": 4, "problem_ids": ["p:t1:0"], "target_bpm": 70,
                "text": "Play bars 2 to 4 at 58 BPM, up 4 BPM per step to 70 BPM, 3 clean reps."}
    agent, _, holder, _ = run_planner(fixture_data, check_ctx, [submit_plan(LIVE_PLAN_BAD, CLEAN_WHOLE), submit_plan(covering, CLEAN_WHOLE)])
    first, second = verdicts(agent)
    assert first["accepted"] is False and second == {"accepted": True}
    assert holder.plan["exercises"][0]["bar_to"] == 4
    assert [line.split(":")[0] for line in holder.rejections][0] == "planner try 1, exercise 0"


def test_the_planner_can_read_the_take_overview_and_its_prompt_says_where_the_tempos_come_from():
    assert "get_take_overview" in PLANNER_TOOLS
    for word in ("target_bpm", "clean_bpm", "bars"):
        assert word in PLANNER_PROMPT


def test_a_sentence_with_a_null_jump_is_a_valid_submission(check_ctx):
    assert CoachSentence.model_validate({**sentence(), "jump": None}).jump is None
    agent, _, holder, _ = run_coach(check_ctx, [submit({**sentence(), "jump": None})])
    assert verdicts(agent) == [{"accepted": True}] and holder.feedback is not None


def test_the_claim_schema_tells_the_model_what_each_value_is():
    value_help = Claim.model_json_schema()["properties"]["value"]["description"]
    assert "PLAYED" in value_help and "played_name" in value_help
    assert "played_name" in COACH_PROMPT


def test_the_rejection_lines_name_the_try_the_item_the_reason_and_the_claim():
    result = {"problems": [{"index": 1, "claim": {"id": "n:t1:2:1", "type": "pitch", "value": "G5"}, "reason": "pitch mismatch: claimed G5, stored F#5"},
                           {"index": None, "claim": None, "reason": "bad exercise count: need 2 to 4 exercises"}]}
    assert describe_rejections("planner", 2, "exercise", result) == [
        'planner try 2, exercise 1: pitch mismatch: claimed G5, stored F#5 [claim {"id": "n:t1:2:1", "type": "pitch", "value": "G5"}]',
        "planner try 2, whole submission: bad exercise count: need 2 to 4 exercises",
    ]
    assert describe_rejections("coach", 1, "sentence", {"problems": []}) == []


def test_live_check_prints_every_rejection_even_when_the_plan_fails(monkeypatch, tmp_path, capsys):
    orchestrator = [tool_turn("get_take_overview", {}), tools_turn(("coach", BRIEF), ("planner", BRIEF)), text_turn()]
    bad_plan = submit_plan(LIVE_PLAN_BAD, LIVE_PLAN_BAD)
    use_agents(monkeypatch, orchestrator, [submit(sentence())], [bad_plan, bad_plan])
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 1
    captured = capsys.readouterr()
    assert "accepted no Planner plan" in captured.err
    lines = [line for line in captured.out.splitlines() if line.startswith("rejected: ")]
    assert any("planner try 1, exercise 0: bars outside range" in line for line in lines)
    assert any("planner try 2, exercise 1: bars outside range" in line for line in lines)
