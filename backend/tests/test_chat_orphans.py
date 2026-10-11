import pytest

from app.agents.holder import ReplyHolder
from app.agents.instructor import build_instructor_agent
from app.agents.orphans import ORPHAN_REASON, orphaned_indexes, starts_with_back_reference
from app.agents.trace import Trace
from tests.fake_model import ScriptedModel, tool_turn
from tests.test_chat_checker import plain
from tests.test_coach_hook import wrong_sentence


def items(*texts):
    return [{"text": t} for t in texts]


@pytest.mark.parametrize("text", [
    "This affects your accuracy.", "that is why", "It helps.", "It's a small fix.", "These notes need air.",
    "Those bars are tricky.", "which matters here.", "  \"This\" one too.",
])
def test_a_sentence_opening_with_a_back_reference_is_recognised(text):
    assert starts_with_back_reference({"text": text})


@pytest.mark.parametrize("item", [
    {"text": "Start with your bell angle."}, {"text": "Thistle is a plant."}, {"text": "Italy is far."},
    {"text": "Keep this steady."}, {"text": 5}, {}, "This", None,
])
def test_other_sentences_are_not_back_references(item):
    assert not starts_with_back_reference(item)


def test_a_back_reference_right_after_a_dropped_sentence_is_an_orphan():
    sentences = items("Bell angle slipped in bar 2.", "This affects bar 8.", "Keep your chin level.")
    assert orphaned_indexes(sentences, {0}) == [1]


def test_an_orphan_makes_the_next_back_reference_an_orphan_too():
    sentences = items("Bar 2 slipped.", "This hurts.", "It also repeats.", "Keep your chin level.", "That helps.")
    assert orphaned_indexes(sentences, {0}) == [1, 2]


def test_a_back_reference_after_a_kept_sentence_stays():
    sentences = items("Bell angle slipped.", "This is fixable.", "Hold it level.")
    assert orphaned_indexes(sentences, {2}) == []
    assert orphaned_indexes(sentences, set()) == []


def test_nothing_is_orphaned_when_the_first_sentence_is_dropped_and_the_next_stands_alone():
    assert orphaned_indexes(items("a", "Keep your chin level."), {0}) == []


def run_chat(check_ctx, script):
    model, holder = ScriptedModel(script), ReplyHolder()
    agent = build_instructor_agent(model, {}, check_ctx, holder, Trace(), [])
    agent("What is the first thing I should work on?")
    return holder


def submit_reply(*sentences):
    return tool_turn("submit_reply", {"sentences": list(sentences)})


def test_a_chat_sentence_left_pointing_at_a_dropped_one_is_dropped_too(check_ctx):
    reply = submit_reply(wrong_sentence(), plain("This affects your breath control."), plain("Keep your breath steady."))
    holder = run_chat(check_ctx, [reply, reply])
    assert [s["text"] for s in holder.reply["sentences"]] == ["Keep your breath steady."]
    assert [d["reasons"][0].split(":")[0] for d in holder.dropped] == ["count mismatch", ORPHAN_REASON.split(":")[0]]


def test_a_chat_reply_with_only_orphans_left_is_refused_so_the_fallback_runs(check_ctx):
    reply = submit_reply(wrong_sentence(), plain("This affects your breath control."))
    holder = run_chat(check_ctx, [reply, reply])
    assert holder.reply is None and holder.tries == 2
