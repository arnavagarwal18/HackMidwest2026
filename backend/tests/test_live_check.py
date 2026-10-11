"""The live check, run on the scripted model: no Bedrock call is made."""
import json

import pytest
from botocore.exceptions import ClientError
from strands.types.exceptions import ModelThrottledException

from app.agents import ai_run, live_check
from app.agents.config import Settings
from app.agents.prompts import COACH_PROMPT, ORCHESTRATOR_PROMPT, PLANNER_PROMPT
from app.agents.smoke_errors import describe_failure
from tests.fake_model import RoutedModel, sleep_turn, text_turn, tool_turn, tools_turn
from tests.planner_helpers import BAR_3, WHOLE_RANGE, submit_plan
from tests.test_checker_feedback import LATE_TEXT, sentence
from tests.test_coach_hook import submit

SETTINGS = Settings(region="us-east-1", text_model="text-model-id", vision_model="vision-model-id", aws_profile="", ai_enabled=True)
BRIEF = {"brief": "Take t1, tier 1 problems p:t1:0 and p:t1:1, trumpet."}
THROTTLED = ClientError({"Error": {"Code": "ThrottlingException", "Message": "Too many tokens per day"}}, "ConverseStream")


@pytest.fixture(autouse=True)
def settings_on(monkeypatch, tmp_path):
    monkeypatch.setattr(live_check, "get_settings", lambda: SETTINGS)
    monkeypatch.setattr(live_check, "LOG_FILE", tmp_path / "live_check.log")


def use_agents(monkeypatch, orchestrator, coach, planner):
    model = RoutedModel({ORCHESTRATOR_PROMPT: orchestrator, COACH_PROMPT: coach, PLANNER_PROMPT: planner})
    monkeypatch.setattr(ai_run, "new_model", lambda: model)
    return model


def working_agents(monkeypatch):
    orchestrator = [tool_turn("get_take_overview", {}), tools_turn(("coach", BRIEF), ("planner", BRIEF)), text_turn()]
    return use_agents(monkeypatch, orchestrator, [submit(sentence())], [submit_plan(BAR_3, WHOLE_RANGE)])


def test_every_stage_runs_and_the_timings_are_printed(monkeypatch, tmp_path, capsys):
    model = working_agents(monkeypatch)
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 0
    out = capsys.readouterr().out
    for stage in ("orchestrator", "coach", "planner", "checker", "total"):
        assert any(line.startswith(stage) and " ms" in line for line in out.splitlines()), stage
    assert "2 checks, 0 failed" in out and "OK: 1 Coach sentences, 2 exercises" in out
    assert all(len(m.script) == 0 for m in model.by_prompt.values())  # each agent played its whole script


def test_the_trace_is_saved_where_asked_and_holds_every_agent(monkeypatch, tmp_path, capsys):
    working_agents(monkeypatch)
    path = tmp_path / "samples" / "live_trace.json"
    assert live_check.main(["--trace-out", str(path)]) == 0
    events = json.loads(path.read_text(encoding="utf-8"))
    assert {e["agent"] for e in events} == {"orchestrator", "coach", "planner", "checker"}
    assert {"check_pass", "model_start", "tool_end"} <= {e["event"] for e in events}
    assert str(path) in capsys.readouterr().out


def test_the_default_trace_path_is_the_agents_samples_folder():
    assert live_check.DEFAULT_TRACE_PATH.parts[-4:] == ("app", "agents", "samples", "live_trace.json")


def test_the_coach_text_is_what_the_checker_accepted(monkeypatch, tmp_path):
    working_agents(monkeypatch)
    live_check.main(["--trace-out", str(tmp_path / "t.json")])
    events = json.loads((tmp_path / "t.json").read_text(encoding="utf-8"))
    assert any(LATE_TEXT in e["detail"] for e in events if e["agent"] == "coach")


@pytest.mark.parametrize("error, line", [
    (THROTTLED, "throttled"),
    (ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "ConverseStream"), "refused access"),
], ids=["throttling", "access_denied"])
def test_a_bedrock_error_in_the_orchestrator_exits_non_zero_with_one_line(monkeypatch, tmp_path, capsys, error, line):
    model = use_agents(monkeypatch, [error], [], [])
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 1
    captured = capsys.readouterr()
    [failure] = captured.err.splitlines()
    assert failure.startswith("FAILED: ") and line in failure
    assert not (tmp_path / "trace.json").exists()
    assert model.by_prompt[ORCHESTRATOR_PROMPT].calls == 1  # the check itself never asks twice


def test_a_throttled_coach_exits_non_zero_and_names_the_throttling(monkeypatch, tmp_path, capsys):
    orchestrator = [tool_turn("get_take_overview", {}), tools_turn(("coach", BRIEF), ("planner", BRIEF)), text_turn()]
    use_agents(monkeypatch, orchestrator, [THROTTLED], [submit_plan(BAR_3, WHOLE_RANGE)])
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 1
    [failure] = capsys.readouterr().err.splitlines()
    assert "throttled" in failure
    assert not (tmp_path / "trace.json").exists()


def test_feedback_the_checker_rejects_exits_non_zero(monkeypatch, tmp_path, capsys):
    orchestrator = [tool_turn("get_take_overview", {}), tools_turn(("coach", BRIEF), ("planner", BRIEF)), text_turn()]
    unfixable = submit(sentence(), problem_ids=("p:t1:9",))
    use_agents(monkeypatch, orchestrator, [unfixable, unfixable], [submit_plan(BAR_3, WHOLE_RANGE)])
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 1
    assert "accepted no Coach feedback" in capsys.readouterr().err


def test_a_run_over_the_time_limit_exits_non_zero(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(ai_run, "TIME_LIMIT_S", 0.2)
    use_agents(monkeypatch, [sleep_turn(5)], [], [])
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 1
    assert "did not finish within 0.2 s" in capsys.readouterr().err


def test_ai_switched_off_exits_non_zero_before_any_agent_runs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(live_check, "get_settings", lambda: Settings("", "", "", "", False))
    monkeypatch.setattr(ai_run, "new_model", lambda: pytest.fail("the model must not be built"))
    assert live_check.main(["--trace-out", str(tmp_path / "trace.json")]) == 1
    assert "AI_ENABLED" in capsys.readouterr().err


def test_an_unwritable_trace_path_exits_non_zero(monkeypatch, tmp_path, capsys):
    working_agents(monkeypatch)
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert live_check.main(["--trace-out", str(blocker / "trace.json")]) == 1


def test_throttling_has_its_own_line_that_says_nothing_was_retried():
    for exc in (THROTTLED, ModelThrottledException("slow down")):
        line = describe_failure(exc, "text model", "text-model-id", SETTINGS)
        assert "throttled" in line and "not retried" in line
