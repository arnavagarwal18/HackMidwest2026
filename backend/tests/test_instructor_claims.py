"""The Instructor must cite the item that stores a fact: an extra-note count lives on the bar (or problem), not on the extra note."""
import json
import re

from app.agents.coach import Claim
from app.agents.context import item_kind
from app.agents.prompts import INSTRUCTOR_PROMPT
from tests.fake_model import text_turn, tool_turn
from tests.test_chat_routes import ai, done_session, say, submit, trace_events, use_script
from tests.test_checker_feedback import claim

EXTRA_TEXT = "Bar 2 has 1 extra note."
_PROMPT_CLAIM_EXAMPLE = re.compile(r"Example: (\{.*?\})\.", re.MULTILINE)


def extra_sentence(claim_id):
    """'Bar 2 has 1 extra note.' with its count claim on `claim_id`; the fixture stores the extra on bar b:t1:2 and x:t1:0 is the extra note."""
    claims = [claim("count", claim_id, 1, field="extra"), claim("bar", "b:t1:2", 2)]
    return {"text": EXTRA_TEXT, "cites": [claim_id], "claims": claims, "jump": {"bar": 2, "time_s": None}}


def ask_with_script(client, fixture_data, monkeypatch, *script):
    ai(monkeypatch)
    model = use_script(monkeypatch, *script)
    session_id = done_session(fixture_data)
    return session_id, model, say(client, session_id, "What should I fix first?").json()["instructor_turn"]


def test_counting_the_extra_note_by_its_own_id_is_rejected_and_the_reply_falls_back(client, fixture_data, monkeypatch):
    bad = submit(extra_sentence("x:t1:0"))
    session_id, model, turn = ask_with_script(client, fixture_data, monkeypatch, tool_turn("get_take_overview", {}), bad, bad)
    assert (turn["mode"], turn["fallback_reason"]) == ("fallback", "checker_rejected")
    failures = [e for e in trace_events(session_id, turn["id"]) if e["event"] == "check_fail"]
    assert len(failures) == 2 and all("count mismatch: x:t1:0 has no stored extra count" in f["detail"] for f in failures)
    assert model.calls == 3


def test_counting_the_extra_notes_on_the_bar_id_is_accepted_as_ai(client, fixture_data, monkeypatch):
    _, model, turn = ask_with_script(client, fixture_data, monkeypatch,
                                     tool_turn("get_bar", {"bar": 2}), submit(extra_sentence("b:t1:2")))
    assert turn["mode"] == "ai" and turn["text"] == EXTRA_TEXT
    assert [(s["checked"], s["cites"]) for s in turn["sentences"]] == [(True, ["b:t1:2"])]


def test_a_rejected_first_try_is_repaired_by_citing_the_bar(client, fixture_data, monkeypatch):
    session_id, model, turn = ask_with_script(client, fixture_data, monkeypatch, submit(extra_sentence("x:t1:0")),
                                              submit(extra_sentence("b:t1:2")))
    assert turn["mode"] == "ai" and turn["dropped"] == [] and model.calls == 2
    verdicts = [e["detail"] for e in trace_events(session_id, turn["id"]) if e["event"] == "tool_end" and e["name"] == "submit_reply"]
    assert "count mismatch: x:t1:0 has no stored extra count" in verdicts[0]


PLAN_ADVICE = ["Start at a tempo where every note is clean.", "Step the tempo up a little after each clean pass."]


def plain_sentences(*texts):
    return [{"text": text, "cites": [], "claims": [], "jump": {"bar": None, "time_s": None}} for text in texts]


def test_a_plan_answer_citing_the_plans_own_ids_and_tempos_is_rejected_and_falls_back(client, fixture_data, monkeypatch):
    """The live failure for 'How fast should I practise?': pl1 is not a measurement id and 100 BPM can't be claimed."""
    sentences = plain_sentences("Start at 100 BPM for all three exercises.", "Step up by 4 BPM after two passes.")
    cited = [{**s, "cites": ["pl1"]} for s in sentences]
    session_id, _, turn = ask_with_script(client, fixture_data, monkeypatch, submit(*cited), submit(*cited))
    assert (turn["mode"], turn["fallback_reason"]) == ("fallback", "checker_rejected")
    failures = [e["detail"] for e in trace_events(session_id, turn["id"]) if e["event"] == "check_fail"]
    assert all("unknown id: pl1" in detail for detail in failures)


def test_a_plan_answer_in_plain_advice_without_digits_is_accepted_as_ai(client, fixture_data, monkeypatch):
    _, _, turn = ask_with_script(client, fixture_data, monkeypatch, tool_turn("get_plan", {}), submit(*plain_sentences(*PLAN_ADVICE)))
    assert turn["mode"] == "ai" and turn["text"] == " ".join(PLAN_ADVICE)


def test_answering_in_plain_text_without_submit_reply_falls_back_as_a_model_error(client, fixture_data, monkeypatch):
    """The live failure for 'Why is bar 3 hard?': the model answered in plain text, which is never shown."""
    _, _, turn = ask_with_script(client, fixture_data, monkeypatch, text_turn("Bar 3 is fine."))
    assert (turn["mode"], turn["fallback_reason"]) == ("fallback", "model_error")


def prompt_examples():
    return [json.loads(text) for text in _PROMPT_CLAIM_EXAMPLE.findall(INSTRUCTOR_PROMPT)]


def test_the_prompt_gives_a_complete_example_for_every_claim_kind_it_explains():
    examples = prompt_examples()
    assert {e["type"] for e in examples} == {"count", "timing_ms", "direction", "tempo_pct", "pitch", "bar"}
    for example in examples:
        assert Claim.model_validate({"field": None, "time_s": None, **example}).id == example["id"]


def test_the_prompts_count_example_cites_a_bar_or_problem_that_stores_counts():
    (count,) = [e for e in prompt_examples() if e["type"] == "count"]
    assert item_kind(count["id"]) in ("bar", "problem") and count["field"] == "extra"

