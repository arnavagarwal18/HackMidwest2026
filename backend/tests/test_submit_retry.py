"""A model that answers in plain text instead of calling its submit tool is asked once more, with the call forced."""
import asyncio
import json
import logging

from app.agents import run
from app.agents.chat_run import FALLBACK_INTRO
from app.agents.coach import build_coach_agent
from app.agents.holder import RunHolder
from app.agents.hooks import FEEDBACK_SUBMIT, PLAN_SUBMIT
from app.agents.planner import build_planner_agent
from app.agents.submit_retry import REPROMPT, invoke_until_submitted
from app.agents.tools import make_tools
from app.agents.trace import Trace
from tests.fake_model import ScriptedModel, text_turn
from tests.planner_helpers import BAR_3, WHOLE_RANGE, submit_plan
from tests.test_chat_routes import TIER1_TEXTS, ai, done_session, plain, say, sentence as reply_sentence, submit as submit_reply, trace_events, use_script
from tests.test_checker_feedback import sentence
from tests.test_coach_hook import submit as submit_feedback, wrong_sentence
from tests.test_run_planner import BOTH_TOOLS, feedback_of, use_agents

UNCHECKED = "Unchecked: you were 40 ms late."
FORCE_SUBMIT_REPLY = {"tool": {"name": "submit_reply"}}


def instructor_turn(client, session_id):
    response = say(client, session_id)
    assert response.status_code == 200
    return response.json()["instructor_turn"]


def last_user_text(agent):
    return agent.messages[-2]["content"][0]["text"]


def test_plain_text_then_a_tool_call_on_the_re_prompt_gives_a_checked_answer(client, fixture_data, monkeypatch, caplog):
    ai(monkeypatch)
    model = use_script(monkeypatch, text_turn(UNCHECKED), submit_reply(reply_sentence(), plain()))
    session_id = done_session(fixture_data)
    with caplog.at_level(logging.WARNING):
        instructor = instructor_turn(client, session_id)
    assert (instructor["mode"], instructor["fallback_reason"]) == ("ai", None)
    assert all(s["checked"] for s in instructor["sentences"]) and UNCHECKED not in json.dumps(instructor)
    assert model.tool_choices == [None, FORCE_SUBMIT_REPLY]
    assert "asking once more" in caplog.text
    assert ("instructor", "reminder") in {(e["agent"], e["event"]) for e in trace_events(session_id, "c2")}


def test_a_re_prompted_answer_that_fails_the_checker_is_still_dropped(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    wrong = {**reply_sentence(), "claims": [{**reply_sentence()["claims"][0], "value": 999}]}
    use_script(monkeypatch, text_turn(UNCHECKED), submit_reply(wrong), submit_reply(wrong))
    instructor = instructor_turn(client, done_session(fixture_data))
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "checker_rejected")


def test_plain_text_twice_falls_back_with_model_error(client, fixture_data, monkeypatch, caplog):
    ai(monkeypatch)
    model = use_script(monkeypatch, text_turn(UNCHECKED), text_turn("Still unchecked: 40 ms late."))
    with caplog.at_level(logging.ERROR):
        instructor = instructor_turn(client, done_session(fixture_data))
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "model_error")
    assert instructor["text"] == " ".join([FALLBACK_INTRO, *TIER1_TEXTS]) and "unchecked" not in json.dumps(instructor).lower()
    assert model.calls == 2 and "still gave no accepted submit_reply" in caplog.text


def test_a_reply_submitted_the_first_time_is_not_re_prompted(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    model = use_script(monkeypatch, submit_reply(reply_sentence()))
    assert instructor_turn(client, done_session(fixture_data))["mode"] == "ai"
    assert model.tool_choices == [None]


def test_ai_disabled_never_calls_the_model(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    model = use_script(monkeypatch)
    assert instructor_turn(client, done_session(fixture_data))["fallback_reason"] == "disabled"
    assert model.calls == 0


def run_submitting(agent, tool_name, accepted, trace):
    asyncio.run(invoke_until_submitted(agent, "Go.", agent_name="coach", tool_name=tool_name, accepted=accepted, trace=trace))


def test_the_coach_is_re_prompted_with_the_call_forced(check_ctx):
    model, holder, trace = ScriptedModel([text_turn("Here is my feedback."), submit_feedback(sentence())]), RunHolder(), Trace()
    agent = build_coach_agent(model, [], check_ctx, holder, trace)
    run_submitting(agent, FEEDBACK_SUBMIT.tool_name, lambda: holder.feedback is not None, trace)
    assert holder.feedback["sentences"][0]["text"] == sentence()["text"]
    assert model.tool_choices == [None, {"tool": {"name": "submit_feedback"}}]
    assert agent.messages[2]["content"][0]["text"] == REPROMPT.format(tool_name="submit_feedback")
    assert agent.model is model  # the forced wrapper is only used for the re-prompt


def test_the_coach_gives_up_after_one_re_prompt(check_ctx, caplog):
    model, holder, trace = ScriptedModel([text_turn("a"), text_turn("b")]), RunHolder(), Trace()
    agent = build_coach_agent(model, [], check_ctx, holder, trace)
    with caplog.at_level(logging.ERROR):
        run_submitting(agent, FEEDBACK_SUBMIT.tool_name, lambda: holder.feedback is not None, trace)
    assert holder.feedback is None and model.calls == 2 and "still gave no accepted submit_feedback" in caplog.text


def test_a_coach_refused_for_good_by_the_checker_is_not_re_prompted(check_ctx):
    model, holder, trace = ScriptedModel([submit_feedback(wrong_sentence()), submit_feedback(wrong_sentence())]), RunHolder(), Trace()
    agent = build_coach_agent(model, [], check_ctx, holder, trace)
    run_submitting(agent, FEEDBACK_SUBMIT.tool_name, lambda: holder.feedback is not None, trace)
    assert holder.feedback is None and model.calls == 2


def test_the_planner_is_re_prompted_with_the_call_forced(fixture_data, check_ctx):
    model, holder, trace = ScriptedModel([text_turn("Here is the plan."), submit_plan(BAR_3, WHOLE_RANGE)]), RunHolder(), Trace()
    tools = make_tools(fixture_data["session_id"], fixture_data["take_id"], get_diagnosis=lambda s, t: fixture_data["diagnosis"],
                       get_form=lambda s, t: fixture_data["form"], get_earlier_takes=lambda s, t: fixture_data["history"])
    agent = build_planner_agent(model, tools, check_ctx, holder, trace)
    run_submitting(agent, PLAN_SUBMIT.tool_name, lambda: holder.plan is not None, trace)
    assert len(holder.plan["exercises"]) == 2
    assert model.tool_choices == [None, {"tool": {"name": "submit_plan"}}]


def test_a_whole_feedback_run_recovers_when_coach_and_planner_both_answer_in_plain_text_first(fixture_data, monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)
    use_agents(monkeypatch, BOTH_TOOLS, coach=[text_turn("My feedback."), submit_feedback(sentence())],
               planner=[text_turn("My plan."), submit_plan(BAR_3, WHOLE_RANGE)])
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], plan["mode"]) == ("ai", "ai") and feedback["fallback_reason"] is None
