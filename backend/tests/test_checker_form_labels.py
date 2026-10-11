import pytest

from app.agents.checker import check_feedback
from app.agents.context import build_context

BELL_FLAG = {
    "id": "f:t1:0",
    "rule": "trumpet_bell_angle",
    "label": "bell too low",
    "direction": "high",
    "start_s": 9.5,
    "end_s": 11.0,
    "peak_s": 10.2,
    "bars": [4],
    "severity": 0.6,
    "confidence": 0.7,
}
PROBLEM = {"id": "p:t1:2", "kind": "late", "bars": [4], "numbers": {"count": 2}}


@pytest.fixture
def bell_ctx():
    return build_context(
        "s1", "t1",
        get_diagnosis=lambda s, t: {"problems": [PROBLEM], "bars": [{"id": "b:t1:4", "bar": 4}]},
        get_form=lambda s, t: {"flags": [BELL_FLAG]},
    )


def form_claim(value):
    return {"type": "form", "id": "f:t1:0", "field": None, "value": value, "time_s": 10.2}


def bell_sentence(text, claims):
    return {"text": text, "cites": ["f:t1:0"], "claims": claims, "jump": {"bar": None, "time_s": None}}


def check(sentence, ctx):
    return check_feedback({"sentences": [sentence], "problem_ids": ["p:t1:2"]}, ctx)


def reasons(result):
    return [p["reason"] for p in result["problems"]]


@pytest.mark.parametrize("value", ["trumpet_bell_angle", "bell too low", "  Bell   TOO low "])
def test_form_claim_accepts_rule_id_or_label(bell_ctx, value):
    result = check(bell_sentence("Your bell is too low here.", [form_claim(value)]), bell_ctx)
    assert result["ok"], reasons(result)


def test_form_claim_with_other_label_fails(bell_ctx):
    result = check(bell_sentence("Your bell is level.", [form_claim("bell too high")]), bell_ctx)
    assert reasons(result) == ["form mismatch: claimed rule bell too high, stored trumpet_bell_angle"]


def test_direction_word_in_claimed_flag_label_counts_as_claimed(bell_ctx):
    result = check(bell_sentence("Your bell is too low.", [form_claim("bell too low")]), bell_ctx)
    assert result["ok"], reasons(result)


def test_direction_word_unrelated_to_form_flag_still_fails(bell_ctx):
    result = check(bell_sentence("Your bell is early.", [form_claim("trumpet_bell_angle")]), bell_ctx)
    assert reasons(result) == ["unclaimed direction: 'early' in text has no matching direction claim"]


def test_flag_label_only_counts_when_the_flag_is_claimed(bell_ctx):
    result = check(bell_sentence("Your bell is too low.", []), bell_ctx)
    assert reasons(result) == ["unclaimed direction: 'low' in text has no matching direction claim"]
