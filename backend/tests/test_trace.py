import json

import pytest

from app import store
from app.agents import ai_run, run
from tests.feedback_helpers import add_diagnosed_take
from tests.fake_model import ScriptedModel, text_turn, tool_turn
from tests.planner_helpers import TOO_FAST, run_planner, submit_plan
from tests.test_checker_feedback import sentence
from tests.test_coach_hook import submit, wrong_sentence
from tests.test_planner_hook import CLEAN_BAR_3, CLEAN_WHOLE
from tests.test_run_ai import ACCESS_DENIED, BRIEF, OVERVIEW


def run_with(monkeypatch, fixture_data, *script, ai=True):
    monkeypatch.setattr(run, "ai_enabled", lambda: ai)
    monkeypatch.setattr(ai_run, "new_model", lambda: ScriptedModel(script))
    session_id, take_id = add_diagnosed_take(fixture_data)
    return session_id, run.run_feedback(session_id, take_id)


def events_of(session_id, feedback_id):
    return json.loads((store.session_dir(session_id) / f"{feedback_id}_trace.json").read_text())


def kinds(events):
    return [(e["agent"], e["event"], e["name"]) for e in events]


def test_a_fake_ai_run_lists_model_calls_tool_calls_and_checker_events_in_order(sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, OVERVIEW, BRIEF, submit(wrong_sentence()), submit(sentence()), text_turn())
    assert kinds(events_of(session_id, feedback_id)) == [
        ("orchestrator", "model_start", "model"), ("orchestrator", "model_end", "model"),
        ("orchestrator", "tool_start", "get_take_overview"), ("orchestrator", "tool_end", "get_take_overview"),
        ("orchestrator", "model_start", "model"), ("orchestrator", "model_end", "model"),
        ("orchestrator", "tool_start", "coach"),
        ("coach", "model_start", "model"), ("coach", "model_end", "model"),
        ("coach", "tool_start", "submit_feedback"), ("checker", "check_fail", "submit_feedback"), ("coach", "tool_end", "submit_feedback"),
        ("coach", "model_start", "model"), ("coach", "model_end", "model"),
        ("coach", "tool_start", "submit_feedback"), ("checker", "check_pass", "submit_feedback"), ("coach", "tool_end", "submit_feedback"),
        ("orchestrator", "tool_end", "coach"),
        ("orchestrator", "model_start", "model"), ("orchestrator", "model_end", "model"),
        ("orchestrator", "fallback", "plan"),
    ]


def test_the_submit_tool_end_shows_the_verdict_the_agent_saw(sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, OVERVIEW, BRIEF, submit(wrong_sentence()), submit(sentence()), text_turn())
    ends = [e for e in events_of(session_id, feedback_id) if (e["agent"], e["event"], e["name"]) == ("coach", "tool_end", "submit_feedback")]
    assert '"accepted": false' in ends[0]["detail"] and '"accepted": true' in ends[1]["detail"]
    assert all(e["duration_ms"] >= 0 for e in events_of(session_id, feedback_id))


def test_details_are_cut_to_500_characters(sessions_root, fixture_data, monkeypatch):
    long_brief = tool_turn("coach", {"brief": "Take t1. " + "x" * 2000})
    session_id, feedback_id = run_with(monkeypatch, fixture_data, OVERVIEW, long_brief, submit(sentence()), text_turn())
    events = events_of(session_id, feedback_id)
    [start] = [e for e in events if (e["agent"], e["event"], e["name"]) == ("orchestrator", "tool_start", "coach")]
    assert len(start["detail"]) == 500 and start["detail"].startswith('{"brief": "Take t1. xxx')
    assert max(len(e["detail"]) for e in events) == 500


def test_a_model_error_still_writes_a_trace_with_the_error_and_a_fallback_event(sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, RuntimeError("model unavailable"))
    events = events_of(session_id, feedback_id)
    assert ("orchestrator", "model_error", "model") in kinds(events)
    assert events[0]["event"] == "model_start"
    assert kinds(events)[-1] == ("orchestrator", "fallback", "model_error")
    assert store.get(session_id).feedback[feedback_id]["mode"] == "fallback"


def test_ai_off_still_writes_a_trace_with_a_fallback_event(sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, ai=False)
    assert kinds(events_of(session_id, feedback_id)) == [("orchestrator", "fallback", "disabled")]


def test_the_route_returns_the_feedback_id_mode_and_events(client, sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, OVERVIEW, BRIEF, submit(sentence()), text_turn())
    response = client.get(f"/sessions/{session_id}/feedback/{feedback_id}/trace")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"feedback_id", "mode", "events"}
    assert (body["feedback_id"], body["mode"]) == (feedback_id, "ai")
    assert body["events"] == events_of(session_id, feedback_id)
    assert set(body["events"][0]) == {"t_ms", "agent", "event", "name", "detail", "duration_ms"}


def test_the_route_reports_a_fallback_mode(client, sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, ai=False)
    body = client.get(f"/sessions/{session_id}/feedback/{feedback_id}/trace").json()
    assert body["mode"] == "fallback" and kinds(body["events"]) == [("orchestrator", "fallback", "disabled")]


def test_an_unknown_session_is_404_session_not_found(client, sessions_root):
    response = client.get("/sessions/nope/feedback/fb1/trace")
    assert response.status_code == 404 and response.json()["error"]["code"] == "session_not_found"


def test_an_unknown_feedback_is_404_feedback_not_found(client, sessions_root, fixture_data, monkeypatch):
    session_id, _ = run_with(monkeypatch, fixture_data, ai=False)
    response = client.get(f"/sessions/{session_id}/feedback/fb99/trace")
    assert response.status_code == 404 and response.json()["error"]["code"] == "feedback_not_found"


def test_a_feedback_without_a_trace_file_is_404_trace_missing(client, sessions_root, fixture_data, monkeypatch):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, ai=False)
    (store.session_dir(session_id) / f"{feedback_id}_trace.json").unlink()
    response = client.get(f"/sessions/{session_id}/feedback/{feedback_id}/trace")
    assert response.status_code == 404 and response.json()["error"]["code"] == "trace_missing"
    assert set(response.json()["error"]) == {"code", "message"}


@pytest.mark.parametrize("content", ["not json", '{"events": []}'], ids=["unparseable", "not_a_list"])
def test_an_unreadable_trace_file_is_a_logged_404_trace_missing(client, sessions_root, fixture_data, monkeypatch, caplog, content):
    session_id, feedback_id = run_with(monkeypatch, fixture_data, ai=False)
    (store.session_dir(session_id) / f"{feedback_id}_trace.json").write_text(content)
    response = client.get(f"/sessions/{session_id}/feedback/{feedback_id}/trace")
    assert response.status_code == 404 and response.json()["error"]["code"] == "trace_missing"
    assert "trace" in caplog.text


def test_the_planner_traces_its_model_and_tool_calls_with_the_checker_verdicts(fixture_data, check_ctx):
    *_, trace = run_planner(fixture_data, check_ctx, [submit_plan(TOO_FAST, CLEAN_WHOLE), submit_plan(CLEAN_BAR_3, CLEAN_WHOLE)])
    assert kinds(trace.events) == [
        ("planner", "model_start", "model"), ("planner", "model_end", "model"),
        ("planner", "tool_start", "submit_plan"), ("checker", "check_fail", "submit_plan"), ("planner", "tool_end", "submit_plan"),
        ("planner", "model_start", "model"), ("planner", "model_end", "model"),
        ("planner", "tool_start", "submit_plan"), ("checker", "check_pass", "submit_plan"), ("planner", "tool_end", "submit_plan"),
    ]


def test_a_planner_run_inside_a_feedback_run_has_planner_events_in_the_trace_file(sessions_root, fixture_data, monkeypatch):
    planner_turn = tool_turn("planner", {"brief": "Plan a slower retake of take t1."})
    monkeypatch.setattr(run, "ai_enabled", lambda: True)
    monkeypatch.setattr(ai_run, "new_model", lambda: ScriptedModel([OVERVIEW, planner_turn, ACCESS_DENIED, text_turn()]))
    session_id, take_id = add_diagnosed_take(fixture_data, cant_tell=True)
    events = events_of(session_id, run.run_feedback(session_id, take_id))
    assert ("orchestrator", "tool_start", "planner") in kinds(events)
    assert ("planner", "model_start", "model") in kinds(events) and ("planner", "model_error", "model") in kinds(events)
