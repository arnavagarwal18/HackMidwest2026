"""The chat coaches answer the same question from their own focus, and never continue another coach's reply."""
import pytest

from app import store
from app.agents import ai_run, run
from app.agents.chat_history import HISTORY_TURNS, history_messages
from app.agents.persona_styles import BEGINNER_INSTRUCTOR, CONCERT_INSTRUCTOR, MARCHING_INSTRUCTOR
from app.agents.prompts import INSTRUCTOR_PROMPT
from tests.fake_model import ScriptedModel, tool_turn
from tests.feedback_helpers import add_diagnosed_take

QUESTION = "what is the first thing i can do to practice"
FOCUS = {  # the opening line of each style's text
    "concert": "You are a precise, patient concert-band trumpet coach.",
    "marching": "You are a direct, encouraging marching-band trumpet coach.",
    "beginner": "You are a warm, straightforward beginner trumpet coach.",
}
STYLE_BLOCKS = {"concert": CONCERT_INSTRUCTOR, "marching": MARCHING_INSTRUCTOR, "beginner": BEGINNER_INSTRUCTOR}


def reply_text(persona_id):
    return f"Reply written by the {persona_id} coach about your practice."


class CapturingModel(ScriptedModel):
    """Answers with a plain reply naming its coach, and keeps the system prompt and messages of the call."""

    def __init__(self, persona_id, captured):
        sentence = {"text": reply_text(persona_id), "cites": [], "claims": [], "jump": {"bar": None, "time_s": None}}
        super().__init__([tool_turn("submit_reply", {"sentences": [sentence]})])
        self.captured, self.persona_id = captured, persona_id

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.captured[self.persona_id] = {"system": system_prompt, "messages": [dict(m) for m in messages]}
        async for event in super().stream(messages, tool_specs, system_prompt, **kwargs):
            yield event


def ask_each(client, monkeypatch, fixture_data, order):
    """One session, the same question put to each coach in turn (the coach changed with PATCH between questions)."""
    monkeypatch.setattr(run, "ai_enabled", lambda: True)
    session_id = add_diagnosed_take(fixture_data, status="done")[0]
    captured = {}
    for persona_id in order:
        monkeypatch.setattr(ai_run, "new_model", lambda persona_id=persona_id: CapturingModel(persona_id, captured))
        assert client.patch(f"/sessions/{session_id}", json={"persona": persona_id}).status_code == 200
        reply = client.post(f"/sessions/{session_id}/chat", json={"message": QUESTION}).json()["instructor_turn"]
        assert (reply["mode"], reply["persona"], reply["text"]) == ("ai", persona_id, reply_text(persona_id))
    return captured


def assistant_text(call):
    return " ".join(block["text"] for m in call["messages"] if m["role"] == "assistant" for block in m["content"])


def whole_prompt(call):
    """Everything the model is sent: the system prompt and the text of every message."""
    return " ".join([call["system"], *(block["text"] for m in call["messages"] for block in m["content"])])


def test_all_four_coaches_get_their_own_prompt_for_the_same_take_and_question(client, fixture_data, monkeypatch):
    calls = ask_each(client, monkeypatch, fixture_data, ["standard", "beginner", "concert", "marching"])
    assert len({whole_prompt(call) for call in calls.values()}) == 4
    assert len({call["system"] for call in calls.values()}) == 4
    for persona_id, focus in FOCUS.items():
        assert focus in calls[persona_id]["system"]
        assert STYLE_BLOCKS[persona_id] in calls[persona_id]["system"]
        assert not [other for other, other_focus in FOCUS.items() if other != persona_id and other_focus in calls[persona_id]["system"]]
    assert not [focus for focus in FOCUS.values() if focus in calls["standard"]["system"]]


def test_a_coachs_prompt_holds_no_text_from_another_coachs_reply(client, fixture_data, monkeypatch):
    order = ["standard", "beginner", "concert", "marching", "concert"]
    captured = []
    monkeypatch.setattr(run, "ai_enabled", lambda: True)
    session_id = add_diagnosed_take(fixture_data, status="done")[0]
    for persona_id in order:
        calls = {}
        monkeypatch.setattr(ai_run, "new_model", lambda persona_id=persona_id, calls=calls: CapturingModel(persona_id, calls))
        client.patch(f"/sessions/{session_id}", json={"persona": persona_id})
        client.post(f"/sessions/{session_id}/chat", json={"message": QUESTION})
        captured.append((persona_id, calls[persona_id]))
    for position, (persona_id, call) in enumerate(captured):
        earlier = captured[:position]
        for other_id in {p for p, _ in earlier if p != persona_id}:
            assert reply_text(other_id) not in whole_prompt(call)  # neither as the coach's own turn nor as background
            assert f"{other_id.capitalize()} coach said" not in whole_prompt(call)
        for own_id in [p for p, _ in earlier if p == persona_id]:
            assert reply_text(own_id) in assistant_text(call)  # the coach's own earlier answers stay its history
        assert [m["role"] for m in call["messages"]][0::2] == ["user"] * len(call["messages"][0::2])  # roles still alternate


def test_a_standard_only_session_sends_the_prompt_and_history_it_always_did(client, fixture_data, monkeypatch):
    calls = ask_each(client, monkeypatch, fixture_data, ["standard"])
    assert calls["standard"]["system"] == INSTRUCTOR_PROMPT
    assert calls["standard"]["messages"] == [{"role": "user", "content": [{"text": QUESTION}]}]


def test_a_standard_session_with_a_second_question_keeps_both_turns_and_adds_no_context(client, fixture_data, monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)
    session_id = add_diagnosed_take(fixture_data, status="done")[0]
    captured = {}
    for _ in range(2):
        monkeypatch.setattr(ai_run, "new_model", lambda: CapturingModel("standard", captured))
        client.post(f"/sessions/{session_id}/chat", json={"message": QUESTION})
    assert captured["standard"]["system"] == INSTRUCTOR_PROMPT
    assert [m["role"] for m in captured["standard"]["messages"]] == ["user", "assistant", "user"]


# ---- the history split ----

def turn(role, text, persona=None):
    return {"role": role, "text": text, **({"persona": persona} if persona else {})}


def test_turns_from_before_personas_count_as_standard():
    turns = [turn("user", "q"), turn("instructor", "old answer")]
    assert history_messages(turns, "standard") == history_messages(turns)
    assert history_messages(turns, "concert") == []


def test_an_exchange_with_another_coach_leaves_the_history_with_its_question():
    turns = [turn("user", "q1"), turn("instructor", "a1", "beginner"), turn("user", "q2"), turn("instructor", "a2", "concert")]
    assert history_messages(turns, "concert") == [{"role": "user", "content": [{"text": "q2"}]},
                                                  {"role": "assistant", "content": [{"text": "a2"}]}]
    assert history_messages(turns, "beginner") == [{"role": "user", "content": [{"text": "q1"}]},
                                                   {"role": "assistant", "content": [{"text": "a1"}]}]


def test_a_question_still_waiting_for_its_reply_stays_in_the_history():
    turns = [turn("user", "q1"), turn("instructor", "a1", "beginner"), turn("user", "q2")]
    assert history_messages(turns, "concert") == [{"role": "user", "content": [{"text": "q2"}]}]


def test_the_history_window_is_the_same_for_every_coach():
    turns = [t for i in range(HISTORY_TURNS) for t in (turn("user", f"q{i}"), turn("instructor", f"a{i}", "marching"))]
    assert len(history_messages(turns, "marching")) == HISTORY_TURNS
    assert len(history_messages(turns)) == 0  # as Standard, every reply in the window is another coach's
