import copy

import pytest

from app.agents.coach import build_coach_agent
from app.agents.holder import RunHolder
from app.agents.trace import Trace
from tests.fake_model import ScriptedModel, text_turn, tool_turn
from tests.test_checker_feedback import claim, output, sentence

WRONG_TEXT = "Bar 3 is late by about 88 ms on 3 notes."


def wrong_sentence():
    claims = [claim("timing_ms", "p:t1:1", 88), claim("direction", "p:t1:1", "late"), claim("count", "p:t1:1", 3, field="late")]
    return sentence(text=WRONG_TEXT, claims=[*claims, claim("bar", "p:t1:1", 3)])


def submit(*sentences, problem_ids=("p:t1:1",)):
    return tool_turn("submit_feedback", {"output": output(*sentences, problem_ids=problem_ids)})


def run_coach(check_ctx, script):
    model, holder, trace = ScriptedModel(script), RunHolder(), Trace()
    agent = build_coach_agent(model, [], check_ctx, holder, trace)
    agent("Explain take t1.")
    return agent, model, holder, trace


def verdicts(agent):
    """The submit_feedback results the model was shown, in order."""
    return [
        block["toolResult"]["content"][0]["json"]
        for message in agent.messages
        for block in message["content"]
        if "toolResult" in block and "json" in block["toolResult"]["content"][0]
    ]


def test_a_wrong_sentence_is_rejected_with_the_reason_then_the_fixed_one_is_accepted(check_ctx):
    agent, model, holder, trace = run_coach(check_ctx, [submit(wrong_sentence()), submit(sentence())])
    first, second = verdicts(agent)
    assert (first["accepted"], first["try"]) == (False, 1)
    [problem] = first["problems"]
    assert problem["sentence"] == 0 and problem["claim"]["value"] == 3 and problem["reason"].startswith("count mismatch")
    assert second == {"accepted": True}
    assert holder.feedback["sentences"][0]["text"] == sentence()["text"]
    assert (holder.dropped, holder.coach_tries, model.calls) == ([], 2, 2)  # the agent stopped without another model turn
    assert [(e["agent"], e["event"]) for e in trace.events] == [("checker", "check_fail"), ("checker", "check_pass")]


def test_the_same_wrong_sentence_twice_is_dropped_and_the_rest_kept(check_ctx):
    script = [submit(wrong_sentence(), sentence()), submit(wrong_sentence(), sentence())]
    agent, model, holder, _ = run_coach(check_ctx, script)
    assert verdicts(agent)[1] == {"accepted": True, "dropped": 1}
    assert [s["text"] for s in holder.feedback["sentences"]] == [sentence()["text"]]
    [dropped] = holder.dropped
    assert dropped["text"] == WRONG_TEXT and dropped["reasons"][0].startswith("count mismatch")
    assert holder.check_counts() == {"coach_tries": 2, "planner_tries": 0, "claims_checked": 8, "claims_failed": 1, "sentences_dropped": 1}
    assert model.calls == 2


def test_dropping_every_sentence_still_accepts_an_empty_output(check_ctx):
    _, _, holder, _ = run_coach(check_ctx, [submit(wrong_sentence()), submit(wrong_sentence())])
    assert holder.feedback["sentences"] == [] and len(holder.dropped) == 1


def test_a_malformed_submission_counts_as_a_try(check_ctx):
    broken = copy.deepcopy(output(sentence()))
    del broken["sentences"][0]["text"]
    agent, _, holder, _ = run_coach(check_ctx, [tool_turn("submit_feedback", {"output": broken}), submit(sentence())])
    first, second = verdicts(agent)
    assert first["accepted"] is False and first["problems"][0]["reason"].startswith("bad submission")
    assert second == {"accepted": True} and holder.coach_tries == 2


def test_output_that_dropping_cannot_repair_is_refused_and_nothing_is_stored(check_ctx):
    script = [submit(sentence(), problem_ids=("p:t1:9",)), submit(sentence(), problem_ids=("p:t1:9",))]
    agent, model, holder, _ = run_coach(check_ctx, script)
    final = verdicts(agent)[1]
    assert (final["accepted"], final["final"]) == (False, True)
    assert final["problems"][0]["reason"].startswith("unknown id")
    assert holder.feedback is None and model.calls == 2


def test_a_model_that_ends_without_submitting_leaves_nothing_accepted(check_ctx):
    _, _, holder, _ = run_coach(check_ctx, [text_turn("here you go")])
    assert holder.feedback is None and holder.coach_tries == 0
