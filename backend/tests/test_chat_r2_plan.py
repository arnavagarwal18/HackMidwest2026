"""LLD-5 r2's Instructor chat test plan, plus the rules that keep unchecked text and secrets from the learner."""
import json
import logging

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from app import store
from app.agents import ai_run
from app.agents.chat_run import FALLBACK_INTRO
from app.agents.credentials import CREDENTIALS_EXPIRED_LINE
from app.agents.instructor import make_chat_tools
from tests.fake_model import text_turn, tool_turn
from tests.test_chat_routes import PLAIN_TEXT, TIER1_TEXTS, ai, done_session, plain, say, sentence, submit, trace_events, use_script
from tests.test_checker_feedback import LATE_TEXT

SECRET_MESSAGE = "placeholder-secret-message-4c7"
UNCITED_LATE = {"text": "Your entrances were late.", "cites": [], "claims": [], "jump": {}}


def instructor_turn(client, session_id, **body):
    response = say(client, session_id, **body)
    assert response.status_code == 200
    return response.json()["instructor_turn"]


def test_a_cited_correct_sentence_and_an_uncited_advice_sentence_are_both_kept_in_order(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    use_script(monkeypatch, tool_turn("get_bar", {"bar": 3}), submit(sentence(), plain()))
    session_id = done_session(fixture_data)
    response = say(client, session_id, "How was bar 3?")
    user, instructor = response.json()["user_turn"], response.json()["instructor_turn"]
    assert response.status_code == 200 and (user["id"], instructor["id"]) == ("c1", "c2")
    assert [(s["text"], s["checked"]) for s in instructor["sentences"]] == [(LATE_TEXT, True), (PLAIN_TEXT, True)]
    assert instructor["sentences"][0]["cites"] == ["p:t1:1"] and instructor["sentences"][1]["cites"] == []
    assert [t["id"] for t in client.get(f"/sessions/{session_id}/chat").json()["turns"]] == ["c1", "c2"]


def test_an_uncited_sentence_with_a_direction_word_is_dropped(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    both = submit(plain(), UNCITED_LATE)
    use_script(monkeypatch, both, both)
    instructor = instructor_turn(client, done_session(fixture_data))
    assert (instructor["mode"], instructor["text"]) == ("ai", PLAIN_TEXT)
    [dropped] = instructor["dropped"]
    assert dropped["text"] == UNCITED_LATE["text"] and dropped["reasons"][0].startswith("uncited")


def test_a_reply_with_no_submit_reply_is_never_shown(client, fixture_data, monkeypatch, caplog):
    ai(monkeypatch)
    use_script(monkeypatch, text_turn("Unchecked: you were 40 ms late."))
    session_id = done_session(fixture_data)
    with caplog.at_level(logging.WARNING):
        instructor = instructor_turn(client, session_id)
    assert (instructor["mode"], instructor["fallback_reason"]) == ("fallback", "model_error")
    assert instructor["text"] == " ".join([FALLBACK_INTRO, *TIER1_TEXTS]) and "Unchecked" not in json.dumps(instructor)
    assert "fallback mode (model_error)" in caplog.text
    assert ("instructor", "fallback") in {(e["agent"], e["event"]) for e in trace_events(session_id, "c2")}


def test_a_rejected_reply_that_is_never_fixed_logs_its_reason(client, fixture_data, monkeypatch, caplog):
    ai(monkeypatch)
    bad = submit(UNCITED_LATE)
    use_script(monkeypatch, bad, bad)
    with caplog.at_level(logging.WARNING):
        instructor = instructor_turn(client, done_session(fixture_data))
    assert instructor["fallback_reason"] == "checker_rejected" and "fallback mode (checker_rejected)" in caplog.text


@pytest.mark.parametrize("error", [
    ClientError({"Error": {"Code": "ExpiredTokenException", "Message": SECRET_MESSAGE}}, "ConverseStream"),
    NoCredentialsError(),
], ids=["expired_token", "no_credentials"])
def test_expired_credentials_go_straight_to_the_fallback_without_leaking_the_message(client, fixture_data, monkeypatch, caplog, error):
    ai(monkeypatch)
    model = use_script(monkeypatch, error)
    session_id = done_session(fixture_data)
    with caplog.at_level(logging.WARNING):
        instructor = instructor_turn(client, session_id)
    assert (instructor["mode"], instructor["fallback_reason"], model.calls) == ("fallback", "model_error", 1)
    assert instructor["text"].startswith(FALLBACK_INTRO)
    assert [r.getMessage() for r in caplog.records].count(CREDENTIALS_EXPIRED_LINE) == 1
    trace_file = (store.session_dir(session_id) / "c2_trace.json").read_text()
    assert ("instructor", "error") in {(e["agent"], e["event"]) for e in trace_events(session_id, "c2")}
    assert all(SECRET_MESSAGE not in text for text in (caplog.text, trace_file, json.dumps(instructor)))


def test_another_error_keeps_only_its_class_in_the_trace(client, fixture_data, monkeypatch):
    ai(monkeypatch)
    use_script(monkeypatch, RuntimeError(SECRET_MESSAGE))
    session_id = done_session(fixture_data)
    instructor_turn(client, session_id)
    error = next(e for e in trace_events(session_id, "c2") if (e["agent"], e["event"]) == ("instructor", "error"))
    assert (error["name"], error["detail"]) == ("RuntimeError", "")


def test_the_model_path_is_the_shared_one(client, fixture_data, monkeypatch):
    """The chat builds its model with ai_run.new_model, the same call (and retry settings) the Coach path uses."""
    ai(monkeypatch)
    built = []
    use_script(monkeypatch, submit(plain()))
    real = ai_run.new_model
    monkeypatch.setattr(ai_run, "new_model", lambda: built.append(1) or real())
    instructor_turn(client, done_session(fixture_data))
    assert built == [1]


def test_a_violin_session_still_gets_trumpet_from_the_score_summary(sessions_root, fixture_data):
    violin_session = store.create("violin").session_id
    take = {"take_id": "t1", "bar_from": 1, "bar_to": 4, "tempo_bpm": 80}
    summary = json.loads(make_chat_tools(violin_session, take)["get_score_summary"]())
    assert summary["instrument"] == "trumpet"
