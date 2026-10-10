"""Trace details: dropped items, error classes only, fallbacks on timeout and model error, a failed write, concurrent adds."""
import json
import threading
from pathlib import Path

import pytest

from app import store
from app.agents import ai_run, run
from app.agents.trace import Trace
from tests.feedback_helpers import add_diagnosed_take
from tests.fake_model import ScriptedModel, sleep_turn, text_turn, tool_turn, tools_turn
from tests.planner_helpers import BAR_3, TOO_FAST, WHOLE_RANGE, submit_plan
from tests.test_checker_feedback import sentence
from tests.test_coach_hook import submit, wrong_sentence
from tests.test_run_ai import ACCESS_DENIED, BRIEF, OVERVIEW
from tests.test_run_planner import use_agents

SECRET_TEXT = "secret-value-never-to-be-traced"


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)


def run_and_load(fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback_id = run.run_feedback(session_id, take_id)
    events = json.loads((store.session_dir(session_id) / f"{feedback_id}_trace.json").read_text())
    return session_id, feedback_id, events


def of_kind(events, event):
    return [e for e in events if e["event"] == event]


def test_every_dropped_sentence_and_exercise_gets_a_dropped_event(sessions_root, fixture_data, monkeypatch):
    two, bad_plan = submit(wrong_sentence(), sentence()), submit_plan(TOO_FAST, BAR_3, WHOLE_RANGE)
    both = [tool_turn("get_take_overview", {}), tools_turn(("coach", {"brief": "Take t1, trumpet."}), ("planner", {"brief": "Take t1, trumpet."})), text_turn()]
    use_agents(monkeypatch, both, coach=[two, two], planner=[bad_plan, bad_plan])
    _, _, events = run_and_load(fixture_data)
    dropped = of_kind(events, "dropped")
    assert sorted((e["agent"], e["name"]) for e in dropped) == [("checker", "submit_feedback"), ("checker", "submit_plan")]
    assert "count mismatch" in next(e for e in dropped if e["name"] == "submit_feedback")["detail"]
    assert "start too fast" in next(e for e in dropped if e["name"] == "submit_plan")["detail"]


def test_a_model_error_traces_a_fallback_with_the_error_class_and_never_the_message(sessions_root, fixture_data, monkeypatch):
    monkeypatch.setattr(ai_run, "new_model", lambda: ScriptedModel([RuntimeError(SECRET_TEXT)]))
    _, _, events = run_and_load(fixture_data)
    [fallback] = of_kind(events, "fallback")
    assert fallback["name"] == "model_error" and fallback["detail"].startswith("error: RuntimeError")
    [model_error] = of_kind(events, "model_error")
    assert model_error["detail"] == "RuntimeError"
    assert SECRET_TEXT not in json.dumps(events)


def test_an_access_denied_model_traces_the_error_class_only(sessions_root, fixture_data, monkeypatch):
    monkeypatch.setattr(ai_run, "new_model", lambda: ScriptedModel([ACCESS_DENIED]))
    _, _, events = run_and_load(fixture_data)
    assert of_kind(events, "model_error")[0]["detail"] == "ClientError"
    assert "not allowed" not in json.dumps(events)
    assert of_kind(events, "fallback")[0]["detail"].startswith("error: ClientError")


def test_a_failing_tool_is_traced_without_its_error_message(sessions_root, fixture_data, monkeypatch):
    from app.agents import tools
    monkeypatch.setattr(ai_run, "new_model", lambda: ScriptedModel([OVERVIEW, text_turn()]))
    original = tools.make_tools

    def failing_tools(*args, **kwargs):
        made = original(*args, **kwargs)
        made["get_take_overview"] = get_take_overview
        return made

    monkeypatch.setattr(ai_run, "make_tools", failing_tools)
    _, _, events = run_and_load(fixture_data)
    assert SECRET_TEXT not in json.dumps(events)
    assert [e["name"] for e in of_kind(events, "tool_error")] == ["get_take_overview"]


def get_take_overview() -> str:
    """Read the take overview."""
    raise RuntimeError(SECRET_TEXT)


def test_a_timeout_writes_a_trace_with_a_timeout_fallback(sessions_root, fixture_data, monkeypatch):
    monkeypatch.setattr(ai_run, "TIME_LIMIT_S", 0.2)
    monkeypatch.setattr(ai_run, "new_model", lambda: ScriptedModel([sleep_turn(5)]))
    _, _, events = run_and_load(fixture_data)
    [fallback] = of_kind(events, "fallback")
    assert fallback["name"] == "timeout" and fallback["detail"].startswith("error: TimeoutError")


def test_a_failed_trace_write_keeps_the_feedback_and_the_route_says_trace_missing(client, fixture_data, monkeypatch, caplog):
    real_write_text = Path.write_text

    def refuse_the_trace(self, *args, **kwargs):
        if self.name.endswith("_trace.json"):
            raise PermissionError("disk is read-only")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(run, "ai_enabled", lambda: False)
    monkeypatch.setattr(Path, "write_text", refuse_the_trace)
    session_id, take_id = add_diagnosed_take(fixture_data)
    feedback_id = run.run_feedback(session_id, take_id)
    assert feedback_id in store.get(session_id).feedback
    assert "Could not write the trace" in caplog.text
    response = client.get(f"/sessions/{session_id}/feedback/{feedback_id}/trace")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "trace_missing")


def test_events_added_from_several_threads_are_all_kept_in_time_order():
    trace = Trace()
    threads = [threading.Thread(target=lambda: [trace.add("coach", "tool_start", "get_bar") for _ in range(200)]) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    times = [e["t_ms"] for e in trace.events]
    assert len(times) == 1600 and times == sorted(times)
