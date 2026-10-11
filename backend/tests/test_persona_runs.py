"""Personas in a feedback run and in chat, with the fake model: prompts, tools, state, trace events, record, fallback."""
import json

import pytest

from app import store
from app.agents import ai_run, run
from app.agents.chat_run import FALLBACK_INTRO
from app.agents.checker import check_plan
from app.agents.context import build_context
from app.agents.holder import RunHolder
from app.agents.persona_run import PersonaRun
from app.agents.personas import BEGINNER, CONCERT, MARCHING, PERSONAS, STANDARD
from app.agents.planner import build_planner_agent
from app.agents.prompts import COACH_PROMPT, INSTRUCTOR_PROMPT, ORCHESTRATOR_PROMPT, PLANNER_PROMPT, with_persona
from app.agents.tools import make_tools
from app.agents.trace import Trace
from tests.fake_model import RoutedModel, ScriptedModel
from tests.feedback_helpers import add_diagnosed_take
from tests.planner_helpers import BAR_3, WHOLE_RANGE, submit_plan
from tests.test_checker_feedback import LATE_TEXT, sentence
from tests.test_chat_routes import ai, done_session, say, submit as submit_reply
from tests.test_coach_hook import submit
from tests.test_run_planner import BOTH_TOOLS

STYLE_PERSONAS = [CONCERT, MARCHING, BEGINNER]
TOP_TO_BOTTOM = ["p:t1:0", "p:t1:1", "p:t1:2"]  # the fixture's tier 1 then tier 2 problems in the ranker's order


class RequestRecordingModel(RoutedModel):
    """A routed model that keeps the first user message each agent (by system prompt) was sent."""

    def __init__(self, scripts):
        super().__init__(scripts)
        self.first_message = {}

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.first_message.setdefault(system_prompt, messages[0]["content"][0]["text"])
        async for event in super().stream(messages, tool_specs, system_prompt, **kwargs):
            yield event


class PromptSpyModel(ScriptedModel):
    """A scripted model that keeps the system prompt of every call."""

    def __init__(self, script):
        super().__init__(script)
        self.prompts = []

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.prompts.append(system_prompt)
        async for event in super().stream(messages, tool_specs, system_prompt, **kwargs):
            yield event


def prompts_for(persona):
    return (ORCHESTRATOR_PROMPT, with_persona(COACH_PROMPT, persona, "coach"), with_persona(PLANNER_PROMPT, persona, "planner"))


def use_persona_agents(monkeypatch, persona, coach_text=LATE_TEXT):
    """Fake Orchestrator, Coach and Planner whose scripts are routed by the persona's exact system prompts."""
    orchestrator, coach, planner = prompts_for(persona)
    model = RequestRecordingModel({orchestrator: BOTH_TOOLS, coach: [submit(sentence(text=coach_text))],
                                   planner: [submit_plan(BAR_3, WHOLE_RANGE)]})
    monkeypatch.setattr(ai_run, "new_model", lambda: model)
    return model


def run_for(fixture_data, persona_id=None):
    session_id, take_id = add_diagnosed_take(fixture_data)
    if persona_id:
        store.update(session_id, "persona", persona_id)
    feedback_id = run.run_feedback(session_id, take_id)
    session = store.get(session_id)
    feedback = session.feedback[feedback_id]
    trace = json.loads((store.session_dir(session_id) / f"{feedback_id}_trace.json").read_text())
    return feedback, session.plans[feedback["plan_id"]], trace


def events(trace, name):
    return [e for e in trace if e["event"] == name]


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)


# ---- Standard is exactly today ----

def test_standard_uses_the_base_prompts_the_old_request_and_leaves_no_persona_events(sessions_root, fixture_data, ai_on, monkeypatch):
    model = use_persona_agents(monkeypatch, STANDARD)  # keyed by the base prompts: a changed prompt would not find its script
    feedback, plan, trace = run_for(fixture_data)
    assert model.first_message[ORCHESTRATOR_PROMPT] == "Feedback for take t1. Read the overview first."
    assert (feedback["mode"], plan["mode"], feedback["persona"]) == ("ai", "ai", "standard")
    assert not events(trace, "persona") and not [e for e in trace if e["event"].startswith("style_")]


def test_standard_planner_has_no_drill_tool_and_the_four_measurement_tools(sessions_root, fixture_data, check_ctx):
    agent = planner_for(fixture_data, check_ctx, PersonaRun())
    assert sorted(agent.tool_names) == ["get_bar", "get_history", "get_take_overview", "list_problems", "submit_plan"]
    assert agent.state.get("persona") == "standard"


# ---- style personas ----

def planner_for(fixture_data, check_ctx, style):
    tools = make_tools(fixture_data["session_id"], fixture_data["take_id"], get_diagnosis=lambda s, t: fixture_data["diagnosis"],
                       get_form=lambda s, t: fixture_data["form"], get_earlier_takes=lambda s, t: fixture_data["history"])
    return build_planner_agent(ScriptedModel([]), tools, check_ctx, RunHolder(), Trace(), style)


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_a_style_persona_run_uses_its_prompts_request_tools_and_trace_event(sessions_root, fixture_data, ai_on, monkeypatch, persona):
    model = use_persona_agents(monkeypatch, persona)
    feedback, plan, trace = run_for(fixture_data, persona.id)
    assert (feedback["mode"], feedback["fallback_reason"], plan["mode"]) == ("ai", None, "ai")  # the unchanged Checker accepted it
    assert feedback["persona"] == persona.id
    request = model.first_message[ORCHESTRATOR_PROMPT]
    assert request.startswith(f"Feedback for take t1. Coaching style: {persona.label}. Focus order: p:t1:")
    assert request.endswith("Read the overview first.")
    [event] = events(trace, "persona")
    detail = json.loads(event["detail"])
    assert (event["name"], detail["id"], detail["tools"][-1]) == (persona.id, persona.id, persona.drill_tool)
    assert sorted(detail["focus_order"]) == sorted(TOP_TO_BOTTOM)


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_a_style_planner_gets_only_its_drill_tool_and_the_agent_state_carries_the_persona(fixture_data, check_ctx, persona):
    style = PersonaRun(persona, ("p:t1:1", "p:t1:0"))
    agent = planner_for(fixture_data, check_ctx, style)
    assert set(agent.tool_names) & {"long_tone_drill", "stamina_set", "two_bar_drill"} == {persona.drill_tool}
    assert agent.system_prompt == with_persona(PLANNER_PROMPT, persona, "planner")
    assert (agent.state.get("persona"), agent.state.get("focus_order")) == (persona.id, ["p:t1:1", "p:t1:0"])


def test_the_focus_order_in_the_request_follows_the_persona(sessions_root, fixture_data, ai_on, monkeypatch):
    model = use_persona_agents(monkeypatch, BEGINNER)
    run_for(fixture_data, "beginner")
    assert "Focus order: p:t1:0, p:t1:1, p:t1:2." in model.first_message[ORCHESTRATOR_PROMPT]  # tier 1 (notes, late), then tier 2


def test_a_stored_persona_that_is_no_longer_offered_runs_as_standard_with_a_trace_event(sessions_root, fixture_data, ai_on, monkeypatch):
    model = use_persona_agents(monkeypatch, STANDARD)
    feedback, _, trace = run_for(fixture_data, "jazz")
    assert feedback["persona"] == "standard" and feedback["mode"] == "ai"
    assert model.first_message[ORCHESTRATOR_PROMPT] == "Feedback for take t1. Read the overview first."
    [event] = events(trace, "persona_unknown")
    assert json.loads(event["detail"]) == {"stored_id": "jazz"}


def test_a_feedback_record_without_a_persona_reads_as_standard(sessions_root, fixture_data, ai_on, monkeypatch):
    use_persona_agents(monkeypatch, STANDARD)
    feedback, _, _ = run_for(fixture_data)
    from app.agents.personas import get_persona
    assert get_persona(feedback.get("persona")) is STANDARD
    assert get_persona({}.get("persona")) is STANDARD


# ---- the style hook ----

def style_events(trace):
    return [(e["event"], e["agent"], json.loads(e["detail"])) for e in trace if e["event"].startswith("style_")]


def test_marching_text_within_15_words_passes_the_style_check_for_coach_and_planner(sessions_root, fixture_data, ai_on, monkeypatch):
    use_persona_agents(monkeypatch, MARCHING)
    _, _, trace = run_for(fixture_data, "marching")
    assert {(event, agent) for event, agent, _ in style_events(trace)} >= {("style_pass", "coach")}


def test_a_style_break_is_traced_but_the_feedback_is_kept_unchanged(sessions_root, fixture_data, ai_on, monkeypatch):
    long_text = "Bar 3 is late by about 88 ms on 2 notes, so keep your feet marking time and play with a full breath every time."
    use_persona_agents(monkeypatch, MARCHING, coach_text=long_text)
    feedback, _, trace = run_for(fixture_data, "marching")
    assert [s["text"] for s in feedback["sentences"]] == [long_text] and feedback["mode"] == "ai"
    fails = [d for event, agent, d in style_events(trace) if event == "style_fail" and agent == "coach"]
    assert fails == [{"agent": "coach", "rule": "max_15_words", "index": 0}]


def test_a_judgment_of_an_unmeasured_quality_is_traced_as_a_style_fail(sessions_root, fixture_data, ai_on, monkeypatch):
    text = "Bar 3 is late by about 88 ms on 2 notes and your attack was weak attack."
    use_persona_agents(monkeypatch, CONCERT, coach_text=text)
    _, _, trace = run_for(fixture_data, "concert")
    assert {"agent": "coach", "rule": "no_unmeasured_judgments", "index": 0} in [d for _, _, d in style_events(trace)]


# ---- AI off: today's fallback for every persona ----

def fallback_fields(feedback, plan):
    clean_feedback = {k: v for k, v in feedback.items() if k not in ("created_at", "duration_ms", "persona")}
    return clean_feedback, plan


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_with_ai_off_every_persona_gets_todays_fallback_and_the_record_names_the_persona(sessions_root, fixture_data, monkeypatch, persona):
    monkeypatch.setattr(run, "ai_enabled", lambda: False)
    baseline = fallback_fields(*run_for(fixture_data)[:2])
    feedback, plan, _ = run_for(fixture_data, persona.id)
    assert fallback_fields(feedback, plan) == baseline
    assert (feedback["persona"], feedback["mode"], feedback["fallback_reason"], plan["mode"]) == (persona.id, "fallback", "disabled", "fallback")


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_every_persona_fallback_plan_passes_the_unchanged_plan_checker(sessions_root, fixture_data, monkeypatch, persona):
    monkeypatch.setattr(run, "ai_enabled", lambda: False)
    _, plan, _ = run_for(fixture_data, persona.id)
    ctx = build_context(fixture_data["session_id"], plan["take_id"], lambda s, t: fixture_data["diagnosis"],
                        get_form=lambda s, t: fixture_data["form"], get_earlier_takes=lambda s, t: fixture_data["history"])
    assert check_plan({"exercises": plan["exercises"]}, ctx)["ok"]


# ---- chat ----

@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_the_instructor_prompt_is_read_at_reply_time_from_the_session_persona(client, fixture_data, monkeypatch, persona):
    ai(monkeypatch)
    session_id = done_session(fixture_data)
    store.update(session_id, "persona", persona.id)
    spy = PromptSpyModel([submit_reply({"text": LATE_TEXT, "cites": ["p:t1:1"], "claims": sentence()["claims"],
                                        "jump": {"bar": 3, "time_s": None}})])
    monkeypatch.setattr(ai_run, "new_model", lambda: spy)
    turn = say(client, session_id).json()["instructor_turn"]
    assert turn["mode"] == "ai" and set(spy.prompts) == {with_persona(INSTRUCTOR_PROMPT, persona, "instructor")}


def test_the_chat_fallback_says_so_with_mode_and_reason_and_keeps_its_text(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id = done_session(fixture_data)
    store.update(session_id, "persona", "marching")
    turn = say(client, session_id).json()["instructor_turn"]
    assert (turn["mode"], turn["fallback_reason"]) == ("fallback", "disabled")
    assert turn["text"].startswith(FALLBACK_INTRO)


def test_odd_problem_data_gives_a_standard_run_not_an_error(sessions_root, fixture_data, ai_on, monkeypatch, caplog):
    use_persona_agents(monkeypatch, STANDARD)
    problems = [{**p, "numbers": ["not", "a", "dict"]} if p["kind"] == "form" else p for p in fixture_data["diagnosis"]["problems"]]
    session_id, take_id = add_diagnosed_take(fixture_data, problems=problems)
    store.update(session_id, "persona", "concert")
    feedback_id = run.run_feedback(session_id, take_id)
    feedback = store.get(session_id).feedback[feedback_id]
    assert (feedback["persona"], feedback["mode"]) == ("standard", "ai")
    assert "Could not build the 'concert' persona run" in caplog.text
