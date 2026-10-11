"""The live Bedrock smoke test script: it skips without its flag, and its result table is checked on scripted models.

Nothing here reaches AWS, except the one test that is skipped unless RUN_LIVE_BEDROCK=1.
"""
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from app.agents import ai_run, run
from app.agents.config import ConfigError, Settings
from app.agents.prompts import COACH_PROMPT, INSTRUCTOR_PROMPT, ORCHESTRATOR_PROMPT, PLANNER_PROMPT
from scripts import live_bedrock_smoke as smoke
from scripts import live_smoke_report as report
from tests.feedback_helpers import add_diagnosed_take
from tests.fake_model import RoutedModel, text_turn, tool_turn, tools_turn
from tests.planner_helpers import BAR_3, WHOLE_RANGE, submit_plan
from tests.test_chat_routes import submit as submit_reply
from tests.test_checker_feedback import sentence
from tests.test_coach_hook import submit, wrong_sentence

BACKEND = Path(__file__).parents[1]
SETTINGS = Settings(region="us-east-1", text_model="text-model-id", vision_model="vision-model-id", aws_profile="", ai_enabled=True)
BRIEF = {"brief": "Take t1, tier 1 problems p:t1:0 and p:t1:1, trumpet."}
ACCESS_DENIED = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "not allowed"}}, "ConverseStream")
ORCHESTRATE = [tool_turn("get_take_overview", {}), tools_turn(("coach", BRIEF), ("planner", BRIEF)), text_turn()]


@pytest.fixture
def fixture_take(fixture_data):
    """A take_source for the script: the diagnosed fixture take, with the feedback run the take pipeline would make."""

    def source(client):
        session_id, take_id = add_diagnosed_take(fixture_data, status="done")
        run.run_feedback(session_id, take_id)
        return session_id, take_id

    return source


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(smoke, "_load_settings", lambda: SETTINGS)
    monkeypatch.setattr(run, "ai_enabled", lambda: True)


def use_agents(monkeypatch, orchestrator=None, coach=None, planner=None, instructor=None):
    scripts = {
        ORCHESTRATOR_PROMPT: orchestrator or ORCHESTRATE,
        COACH_PROMPT: coach or [submit(sentence())],
        PLANNER_PROMPT: planner or [submit_plan(BAR_3, WHOLE_RANGE)],
        INSTRUCTOR_PROMPT: instructor or [tool_turn("get_take_overview", {}), submit_reply(sentence())],
    }
    model = RoutedModel(scripts)
    monkeypatch.setattr(ai_run, "new_model", lambda: model)
    return model


def smoke_run(tmp_path, take_source):
    code = smoke.run_live(tmp_path / "out" / "results.json", take_source)
    saved = json.loads((tmp_path / "out" / "results.json").read_text(encoding="utf-8"))
    return code, {row["step"]: row for row in saved["steps"]}, saved


def test_without_the_flag_the_script_skips_and_exits_zero(tmp_path):
    env = {key: value for key, value in os.environ.items() if key != smoke.FLAG}
    done = subprocess.run([sys.executable, str(BACKEND / "scripts" / "live_bedrock_smoke.py"), "--out", str(tmp_path / "r.json")],
                          capture_output=True, text=True, env=env, cwd=BACKEND, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "Skipped" in done.stdout and smoke.FLAG in done.stdout
    assert not (tmp_path / "r.json").exists()


def test_a_flag_other_than_1_also_skips(monkeypatch, capsys):
    monkeypatch.setenv(smoke.FLAG, "true")
    monkeypatch.setattr(smoke, "run_live", lambda *a, **k: pytest.fail("must not run"))
    assert smoke.main([]) == 0
    assert "Skipped" in capsys.readouterr().out


def test_every_step_passing_prints_a_table_and_saves_the_results(tmp_path, monkeypatch, ai_on, fixture_take, capsys):
    use_agents(monkeypatch)
    code, rows, saved = smoke_run(tmp_path, fixture_take)
    assert code == 0 and saved["all_passed"] is True
    assert list(rows) == ["settings", "feedback: coach", "feedback: planner", "instructor chat"]
    assert {row["status"] for row in rows.values()} == {"pass"}
    assert [rows[name]["checker_accepted"] for name in ("feedback: coach", "feedback: planner", "instructor chat")] == [True] * 3
    assert [rows[name]["mode"] for name in ("feedback: coach", "feedback: planner", "instructor chat")] == ["ai"] * 3
    assert all(row["latency_s"] is not None for name, row in rows.items() if name != "settings")
    assert saved["settings_present"] == {"BEDROCK_REGION": True, "BEDROCK_TEXT_MODEL": True, "BEDROCK_VISION_MODEL": True}
    out = capsys.readouterr().out
    assert out.splitlines()[-3:-2] and "instructor chat" in out and "accepted" in out


def test_no_setting_value_reaches_the_output_or_the_results(tmp_path, monkeypatch, ai_on, fixture_take, capsys):
    use_agents(monkeypatch)
    smoke_run(tmp_path, fixture_take)
    everything = capsys.readouterr().out + (tmp_path / "out" / "results.json").read_text(encoding="utf-8")
    assert "BEDROCK_TEXT_MODEL=yes" in everything
    for value in (SETTINGS.region, SETTINGS.text_model, SETTINGS.vision_model):
        assert value not in everything


def test_a_coach_the_checker_rejects_fails_with_checker_rejected(tmp_path, monkeypatch, ai_on, fixture_take):
    bad = submit(wrong_sentence())
    use_agents(monkeypatch, coach=[bad, bad])
    code, rows, _ = smoke_run(tmp_path, fixture_take)
    coach = rows["feedback: coach"]
    assert code == 1 and (coach["status"], coach["mode"], coach["reason"], coach["checker_accepted"]) == ("fail", "fallback", "checker_rejected", False)
    assert rows["feedback: planner"]["status"] == "pass" and rows["instructor chat"]["status"] == "pass"


def test_a_model_error_fails_every_agent_with_model_error_and_its_class(tmp_path, monkeypatch, ai_on, fixture_take):
    use_agents(monkeypatch, orchestrator=[ACCESS_DENIED], instructor=[ACCESS_DENIED])
    code, rows, _ = smoke_run(tmp_path, fixture_take)
    assert code == 1
    for name in ("feedback: coach", "feedback: planner", "instructor chat"):
        assert (rows[name]["status"], rows[name]["mode"], rows[name]["reason"], rows[name]["checker_accepted"]) == ("fail", "fallback", "model_error", None)
    assert rows["feedback: coach"]["error_class"] == "ClientError"


def test_a_planner_the_checker_rejects_is_told_apart_from_a_coach_that_passed(tmp_path, monkeypatch, ai_on, fixture_take):
    bad_plan = submit_plan({**BAR_3, "start_bpm": 66})
    use_agents(monkeypatch, planner=[bad_plan, bad_plan])
    _, rows, _ = smoke_run(tmp_path, fixture_take)
    assert rows["feedback: coach"]["status"] == "pass"
    planner = rows["feedback: planner"]
    assert (planner["status"], planner["mode"], planner["reason"], planner["checker_accepted"]) == ("fail", "fallback", "checker_rejected", False)


def test_a_take_that_cannot_be_made_fails_it_and_skips_what_needs_it(tmp_path, monkeypatch, ai_on):
    use_agents(monkeypatch)

    def broken(client):
        raise RuntimeError("upload failed")

    code, rows, _ = smoke_run(tmp_path, broken)
    assert code == 1
    assert (rows["take flow"]["status"], rows["take flow"]["reason"], rows["take flow"]["error_class"]) == ("fail", "step_crashed", "RuntimeError")
    assert {rows[name]["status"] for name in ("feedback: coach", "feedback: planner", "instructor chat")} == {"skipped"}


def test_ai_disabled_stops_after_the_settings_row_without_running_any_agent(tmp_path, monkeypatch, ai_on):
    monkeypatch.setattr(smoke, "_load_settings", lambda: replace(SETTINGS, ai_enabled=False))
    code, rows, _ = smoke_run(tmp_path, lambda client: pytest.fail("must not make a take"))
    assert code == 1 and list(rows) == ["settings"] and rows["settings"]["reason"] == "ai_disabled"


def test_a_missing_setting_name_is_reported_without_running(tmp_path, monkeypatch):
    def broken():
        raise ConfigError("AI_ENABLED is true but BEDROCK_VISION_MODEL is empty.")

    monkeypatch.setattr(smoke, "_load_settings", broken)
    code, rows, _ = smoke_run(tmp_path, lambda client: pytest.fail("must not make a take"))
    assert code == 1 and list(rows) == ["settings"] and rows["settings"]["reason"] == "bad_settings"
    assert (tmp_path / "out" / "results.log").read_text(encoding="utf-8").count("ConfigError") >= 1  # the failure is kept in the log


def test_unwritable_results_exit_nonzero_and_say_where(tmp_path, monkeypatch, ai_on, fixture_take, capsys):
    use_agents(monkeypatch)
    monkeypatch.setattr(smoke, "write_json", lambda path, payload: False)
    assert smoke.run_live(tmp_path / "out" / "results.json", fixture_take) == 1
    assert "could not write the results" in capsys.readouterr().err


def test_the_table_has_a_row_per_step_with_dashes_for_what_does_not_apply():
    lines = report.table_lines([report.StepResult("a", report.PASS, 1.234, True, "ai"), report.skipped("b", "no take")])
    assert lines[0].split() == ["step", "result", "seconds", "checker", "mode", "reason"]
    assert lines[1].split() == ["a", "pass", "1.2", "accepted", "ai", "-"]
    assert lines[2].split() == ["b", "skipped", "-", "n/a", "-", "skipped"]


@pytest.mark.skipif(os.environ.get(smoke.FLAG) != "1", reason="set RUN_LIVE_BEDROCK=1 to call real Bedrock")
def test_live_every_path_runs_once_on_real_bedrock(tmp_path):
    assert smoke.main(["--out", str(tmp_path / "live.json")]) == 0
