import json
import threading
import time

import pytest
from botocore.exceptions import ClientError

from app import store
from app.agents import ai_run, chat_routes, run
from app.agents.chat_run import FALLBACK_INTRO, NO_TAKE_TEXT
from app.agents.instructor import HISTORY_TURNS, history_messages, make_chat_tools
from app.agents.trace import AGENTS
from app.takes.take_store import add_take
from tests.feedback_helpers import add_diagnosed_take
from tests.fake_model import ScriptedModel, slow, sleep_turn, tool_turn
from tests.test_checker_feedback import LATE_TEXT, sentence
from tests.test_coach_hook import wrong_sentence

PLAIN_TEXT = "Keep your breath steady and your lips relaxed."
TIER1_TEXTS = ["Bars 2 and 4 have wrong or missed notes.", "Bar 3 is late."]
ACCESS_DENIED = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "not allowed"}}, "ConverseStream")


def plain():
    return {"text": PLAIN_TEXT, "cites": [], "claims": [], "jump": {"bar": None, "time_s": None}}


def submit(*sentences):
    return tool_turn("submit_reply", {"sentences": list(sentences)})


def use_script(monkeypatch, *script, model_class=ScriptedModel):
    model = model_class(script)
    monkeypatch.setattr(ai_run, "new_model", lambda: model)
    return model


def ai(monkeypatch, enabled=True):
    monkeypatch.setattr(run, "ai_enabled", lambda: enabled)


def done_session(fixture_data):
    return add_diagnosed_take(fixture_data, status="done")[0]


def say(client, session_id, message="How did I do?", **body):
    return client.post(f"/sessions/{session_id}/chat", json={"message": message, **body})


def add_take_like_t1(session_id, status):
    t1 = store.get(session_id).takes["t1"]
    return add_take(session_id, lambda take_id: {**{k: v for k, v in t1.items() if k != "take_id"}, "status": status}, lambda take: None)


def trace_events(session_id, turn_id):
    return json.loads((store.session_dir(session_id) / f"{turn_id}_trace.json").read_text())


class RecordingModel(ScriptedModel):
    """A scripted model that keeps the messages of its first call."""

    async def stream(self, messages, *args, **kwargs):
        if not hasattr(self, "seen"):
            self.seen = [m for m in messages]
        async for event in super().stream(messages, *args, **kwargs):
            yield event


def test_instructor_is_a_traced_agent():
    assert "instructor" in AGENTS


# ---- the AI path ----

def test_the_instructor_answers_with_checked_sentences_and_both_turns_are_saved(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    model = use_script(monkeypatch, tool_turn("get_take_overview", {}), submit(plain(), sentence()))
    session_id = done_session(fixture_data)
    response = say(client, session_id, "How did I do?")
    assert response.status_code == 200
    user, instructor = response.json()["user_turn"], response.json()["instructor_turn"]
    assert (user["id"], user["role"], user["text"], user["take_id"]) == ("c1", "user", "How did I do?", "t1")
    assert (instructor["id"], instructor["role"], instructor["mode"], instructor["take_id"]) == ("c2", "instructor", "ai", "t1")
    assert instructor["text"] == f"{PLAIN_TEXT} {LATE_TEXT}"
    assert [(s["text"], s["checked"], s["mode"]) for s in instructor["sentences"]] == [(PLAIN_TEXT, True, "ai"), (LATE_TEXT, True, "ai")]
    assert instructor["sentences"][1]["cites"] == ["p:t1:1"] and instructor["dropped"] == []
    assert model.calls == 2
    assert client.get(f"/sessions/{session_id}/chat").json() == {"turns": [user, instructor]}


def test_the_trace_has_instructor_and_checker_events(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    use_script(monkeypatch, tool_turn("get_take_overview", {}), submit(sentence()))
    session_id = done_session(fixture_data)
    turn_id = say(client, session_id).json()["instructor_turn"]["id"]
    events = trace_events(session_id, turn_id)
    pairs = {(e["agent"], e["event"]) for e in events}
    assert {("instructor", "model_start"), ("instructor", "tool_start"), ("instructor", "tool_end"), ("checker", "check_pass")} <= pairs
    assert {"get_take_overview", "submit_reply"} <= {e["name"] for e in events if e["agent"] == "instructor" and e["event"] == "tool_start"}


def test_the_checker_hook_runs_after_the_trace_hook(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    use_script(monkeypatch, submit(sentence()))
    session_id = done_session(fixture_data)
    events = trace_events(session_id, say(client, session_id).json()["instructor_turn"]["id"])
    names = [(e["agent"], e["event"]) for e in events if e["name"] == "submit_reply" or e["agent"] == "checker"]
    assert names == [("instructor", "tool_start"), ("checker", "check_pass"), ("instructor", "tool_end")]


def test_a_rejected_reply_is_fixed_on_the_second_try(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    use_script(monkeypatch, submit(wrong_sentence()), submit(sentence()))
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["mode"], instructor["text"], instructor["dropped"]) == ("ai", LATE_TEXT, [])


def test_try_two_drops_the_failing_sentence_and_keeps_the_rest(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    both = submit(plain(), wrong_sentence())
    use_script(monkeypatch, both, both)
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["mode"], instructor["text"]) == ("ai", PLAIN_TEXT)
    [dropped] = instructor["dropped"]
    assert dropped["text"] == wrong_sentence()["text"] and dropped["reasons"][0].startswith("count mismatch")


def test_an_uncited_number_is_dropped_but_an_uncited_plain_sentence_is_kept(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    uncited = {"text": "You played 12 notes.", "cites": [], "claims": [], "jump": {}}
    two = submit(plain(), uncited)
    use_script(monkeypatch, two, two)
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert instructor["text"] == PLAIN_TEXT and instructor["dropped"][0]["reasons"][0].startswith("uncited")


def test_when_nothing_passes_the_fallback_reply_is_used(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    bad = submit(wrong_sentence())
    use_script(monkeypatch, bad, bad)
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "checker_rejected")
    assert instructor["text"] == " ".join([FALLBACK_INTRO, *TIER1_TEXTS])


def test_the_model_sees_the_new_message_after_the_last_10_turns(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id = done_session(fixture_data)
    for i in range(7):
        assert say(client, session_id, f"question {i}").status_code == 200  # 14 turns
    ai(monkeypatch)
    model = use_script(monkeypatch, submit(plain()), model_class=RecordingModel)
    say(client, session_id, "the new question")
    texts = [m["content"][0]["text"] for m in model.seen]
    assert len(texts) == HISTORY_TURNS + 1 and texts[-1] == "the new question"
    assert [m["role"] for m in model.seen] == ["user", "assistant"] * 5 + ["user"]
    assert texts[0] == "question 2"


# ---- default and chosen take ----

def test_the_default_take_is_the_latest_done_take(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id = done_session(fixture_data)
    add_take_like_t1(session_id, "done")
    add_take_like_t1(session_id, "processing")
    assert say(client, session_id).json()["instructor_turn"]["take_id"] == "t2"


def test_an_explicit_take_id_is_used(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id = done_session(fixture_data)
    add_take_like_t1(session_id, "done")
    assert say(client, session_id, take_id="t1").json()["user_turn"]["take_id"] == "t1"


# ---- fallback ----

def test_with_ai_off_the_reply_is_the_tier1_sentences(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "disabled")
    assert instructor["text"] == f"{FALLBACK_INTRO} {TIER1_TEXTS[0]} {TIER1_TEXTS[1]}"
    assert [s["mode"] for s in instructor["sentences"]] == ["fallback", "fallback"]
    assert instructor["sentences"][1]["cites"] == ["p:t1:1"]
    assert ("instructor", "fallback") in {(e["agent"], e["event"]) for e in trace_events(session_id, "c2")}


def test_with_no_take_the_reply_says_to_record_one_without_calling_the_model(client, monkeypatch):
    ai(monkeypatch)
    model = use_script(monkeypatch)
    session_id = store.create("trumpet").session_id
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["text"], instructor["mode"], instructor["take_id"], instructor["sentences"]) == (NO_TAKE_TEXT, "fallback", None, [])
    assert model.calls == 0


def test_a_timeout_falls_back(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    monkeypatch.setattr(ai_run, "TIME_LIMIT_S", 0.2)
    use_script(monkeypatch, sleep_turn(3))
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "timeout")
    assert instructor["text"].startswith(FALLBACK_INTRO)


def test_a_model_error_falls_back_and_is_logged(client, fixture_data, monkeypatch, caplog):
    ai(monkeypatch)
    use_script(monkeypatch, ACCESS_DENIED)
    session_id = done_session(fixture_data)
    instructor = say(client, session_id).json()["instructor_turn"]
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "model_error")
    assert "ClientError" in caplog.text
    assert ("instructor", "error") in {(e["agent"], e["event"]) for e in trace_events(session_id, "c2")}


def test_unreadable_ai_settings_fall_back(client, fixture_data, monkeypatch):
    def broken():
        raise RuntimeError("bad settings")

    monkeypatch.setattr(run, "ai_enabled", broken)
    session_id = done_session(fixture_data)
    assert say(client, session_id).json()["instructor_turn"]["fallback_reason"] == "disabled"


# ---- errors ----

def test_an_unknown_session_is_404_on_both_routes(client):
    for response in (say(client, "nosuchsession"), client.get("/sessions/nosuchsession/chat")):
        assert response.status_code == 404 and response.json()["error"]["code"] == "session_not_found"


def test_an_unknown_take_is_404(client, fixture_data):
    session_id = done_session(fixture_data)
    response = say(client, session_id, take_id="t9")
    assert response.status_code == 404 and response.json()["error"]["code"] == "take_not_found"
    assert client.get(f"/sessions/{session_id}/chat").json() == {"turns": []}


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "   "}, {"message": "x" * 1001}, {}, {"message": 5}])
def test_a_bad_message_is_422_and_saves_nothing(client, fixture_data, body):
    session_id = done_session(fixture_data)
    response = client.post(f"/sessions/{session_id}/chat", json=body)
    assert response.status_code == 422 and response.json()["error"]["code"] == "bad_request"
    assert client.get(f"/sessions/{session_id}/chat").json() == {"turns": []}


def test_a_message_of_exactly_1000_characters_is_accepted(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    assert say(client, done_session(fixture_data), "x" * 1000).status_code == 200


def test_a_new_session_has_an_empty_chat(client):
    session_id = store.create("trumpet").session_id
    assert client.get(f"/sessions/{session_id}/chat").json() == {"turns": []}


def test_a_second_message_during_a_reply_is_409_but_other_sessions_are_not_held_up(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    use_script(monkeypatch, slow(submit(plain()), 1.0))
    busy, other = done_session(fixture_data), done_session(fixture_data)
    first = {}
    worker = threading.Thread(target=lambda: first.update(response=say(client, busy)))
    worker.start()
    deadline = time.monotonic() + 5
    while not (chat_routes._reply_locks.get(busy) and chat_routes._reply_locks[busy].locked()) and time.monotonic() < deadline:
        time.sleep(0.01)
    second = say(client, busy, "and another thing")
    assert second.status_code == 409
    assert second.json()["error"] == {"code": "wrong_state", "message": "Instructor is already replying."}
    ai(monkeypatch, enabled=False)
    assert say(client, other).status_code == 200
    worker.join(10)
    assert first["response"].status_code == 200
    assert [t["role"] for t in client.get(f"/sessions/{busy}/chat").json()["turns"]] == ["user", "instructor"]
    assert say(client, busy).status_code == 200  # the lock was released


# ---- the Instructor's own tools and history ----

def test_history_starts_with_a_learner_message_and_keeps_text_only():
    turns = [{"role": "instructor", "text": "hi"}, {"role": "user", "text": "q"}, {"role": "instructor", "text": "a"}]
    assert history_messages(turns) == [{"role": "user", "content": [{"text": "q"}]}, {"role": "assistant", "content": [{"text": "a"}]}]


def test_get_plan_returns_the_takes_plan_or_null(sessions_root, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    tools = make_chat_tools(session_id, store.get(session_id).takes[take_id])
    assert tools["get_plan"]() == "null"
    run.run_feedback(session_id, take_id)
    plan = json.loads(tools["get_plan"]())
    assert plan["take_id"] == take_id and len(plan["exercises"]) == 3 and "progress" not in plan
    store.update(session_id, "progress", {plan["id"]: {"reps": 1}})
    assert json.loads(tools["get_plan"]())["progress"] == {"reps": 1}


def test_get_score_summary_has_the_takes_bars_and_target_tempo(sessions_root, fixture_data, caplog):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    summary = json.loads(make_chat_tools(session_id, store.get(session_id).takes[take_id])["get_score_summary"]())
    assert summary == {"title": None, "instrument": "trumpet", "bars": None, "bar_from": 1, "bar_to": 4, "target_bpm": 80}
    assert "No confirmed score" in caplog.text
