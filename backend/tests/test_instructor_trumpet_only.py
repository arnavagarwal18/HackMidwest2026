"""The Instructor is for trumpet only: its prompt, its tool descriptions and every fallback reply name no other instrument."""
import re

import pytest

from app import store
from app.agents.chat_run import FALLBACK_INTRO, NO_TAKE_TEXT
from app.agents.fallback import CANT_TELL_TEXT
from app.agents.instructor import make_chat_tools
from app.agents.prompts import INSTRUCTOR_PROMPT
from tests.test_chat_routes import ai, done_session, say

OTHER_INSTRUMENTS = ("violin", "viola", "cello", "bass", "piano", "keyboard", "guitar", "ukulele", "banjo", "flute", "piccolo",
                     "oboe", "clarinet", "bassoon", "sax", "saxophone", "trombone", "tuba", "horn", "cornet", "drum", "drums",
                     "harp", "recorder", "harmonica", "accordion", "voice", "singing")
TRUMPET_TOPICS = ("breath", "tonguing", "valve", "slur", "range", "posture")
_OTHER = re.compile(rf"\b(?:{'|'.join(OTHER_INSTRUMENTS)})s?\b", re.IGNORECASE)


def other_instruments_in(text):
    return sorted({m.group(0).lower() for m in _OTHER.finditer(text)})


def test_the_detector_finds_another_instrument():
    assert other_instruments_in("Try this on the violin or a Piano.") == ["piano", "violin"]
    assert other_instruments_in("Keep your breath steady and tongue each note.") == []


def test_the_system_prompt_is_trumpet_only():
    assert "trumpet" in INSTRUCTOR_PROMPT.lower()
    assert other_instruments_in(INSTRUCTOR_PROMPT) == []


def test_the_system_prompt_fails_the_check_when_it_names_another_instrument():
    assert other_instruments_in(INSTRUCTOR_PROMPT + " Treat every learner like a violin student.") == ["violin"]


def test_the_system_prompt_keeps_advice_to_the_trumpet_topics():
    assert all(topic in INSTRUCTOR_PROMPT.lower() for topic in TRUMPET_TOPICS)


def test_the_tool_descriptions_name_no_other_instrument():
    tools = make_chat_tools("s1", {"take_id": "t1", "bar_from": 1, "bar_to": 4})
    for name, fn in tools.items():
        assert other_instruments_in(fn.__doc__ or "") == [], name


@pytest.mark.parametrize("text", [FALLBACK_INTRO, NO_TAKE_TEXT, CANT_TELL_TEXT], ids=["intro", "no_take", "cant_tell"])
def test_the_fixed_fallback_texts_name_no_other_instrument(text):
    assert other_instruments_in(text) == []


def test_the_fallback_replies_name_no_other_instrument(client, fixture_data, monkeypatch):
    ai(monkeypatch, enabled=False)
    session_id = done_session(fixture_data)
    empty_session = store.create("trumpet").session_id
    for sid in (session_id, empty_session):
        reply = say(client, sid).json()["instructor_turn"]
        assert reply["mode"] == "fallback"
        assert other_instruments_in(reply["text"]) == []
