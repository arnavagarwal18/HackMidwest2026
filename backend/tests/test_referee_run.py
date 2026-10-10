import copy
import time

import pytest

from app.agents.trace import Trace
from app.score import compare as compare_module
from app.score.compare import CompareResult
from app.score.referee import agent, apply, run
from tests.referee_helpers import (  # noqa: F401
    FOUR_QUARTERS, SETTINGS_OFF, ai_on, compare_of, make_reading, make_score, photo, stub_factory,
)

D5_QUARTERS = [("D5", "quarter")] * 4
C5_QUARTERS = [("C5", "quarter")] * 4
SHORT_BAR = [("E5", "quarter")] * 3


@pytest.fixture
def case():
    """Bar 2: homr is a quarter short and the reader is right. Bar 3: both look fine but differ."""
    score = make_score([FOUR_QUARTERS, SHORT_BAR, C5_QUARTERS, FOUR_QUARTERS, FOUR_QUARTERS])
    reading = make_reading({1: FOUR_QUARTERS, 2: D5_QUARTERS, 3: D5_QUARTERS, 4: FOUR_QUARTERS, 5: FOUR_QUARTERS})
    return score, reading, compare_of(score, reading)


def rule_bar_2_reader_and_bar_3_neither(session, cancel):
    session.list_doubtful_bars()
    session.get_bar(2)
    session.submit_ruling(2, "reader", "the reader counts four beats", 0.9)
    session.get_bar(3)
    session.look_at_bar(3)
    session.submit_ruling(3, "neither", "both look plausible", 0.6)


def test_stub_run_replaces_the_accepted_bar_and_keeps_the_other_doubtful(ai_on, case, photo):
    score, reading, comparison = case
    trace = Trace()
    result = run(score, reading, comparison, photo, trace=trace,
                 agent_factory=stub_factory(rule_bar_2_reader_and_bar_3_neither))

    assert result.referee["status"] == "done" and result.referee["reason"] is None
    assert result.referee["model_id"] == "vision-model"
    assert isinstance(result.referee["elapsed_ms"], int)
    assert [(r["bar"], r["pick"], r["accepted"], r["rejected_because"]) for r in result.referee["rulings"]] == [
        (2, "reader", True, None), (3, "neither", False, "neither")]
    bar_2 = result.score.bars[1]
    assert [(n.name, n.dur_beats, n.start_beat, n.pitch_midi) for n in bar_2.notes] == [
        ("D5", 1.0, 4.0, 74), ("D5", 1.0, 5.0, 74), ("D5", 1.0, 6.0, 74), ("D5", 1.0, 7.0, 74)]
    assert [n.idx for n in bar_2.notes] == [0, 1, 2, 3]
    assert result.score.bars[2] == score.bars[2]
    assert len(result.compare.doubtful_bars) == 1
    assert result.compare.doubtful_bars[0]["bar"] == 3
    assert result.compare.doubtful_bars[0]["referee_note"] == "both look plausible"
    assert result.compare.double_checked is True
    events = [(e["agent"], e["event"], e["name"]) for e in trace.events]
    assert events == [
        ("referee", "tool", "list_doubtful_bars"), ("referee", "tool", "get_bar"), ("referee", "ruling", "bar 2"),
        ("referee", "tool", "get_bar"), ("referee", "tool", "look_at_bar"), ("referee", "ruling", "bar 3")]


def test_the_inputs_are_not_changed(ai_on, case, photo):
    score, reading, comparison = case
    before = copy.deepcopy((score, comparison))
    run(score, reading, comparison, photo, agent_factory=stub_factory(rule_bar_2_reader_and_bar_3_neither))
    assert (score, comparison) == before


def test_bars_the_referee_did_not_rule_on_stay_doubtful_with_a_null_note(ai_on, case, photo):
    score, reading, comparison = case

    def only_bar_2(session, cancel):
        session.submit_ruling(2, "reader", "four beats", 0.9)

    result = run(score, reading, comparison, photo, agent_factory=stub_factory(only_bar_2))
    assert result.referee["status"] == "done"
    assert [(d["bar"], d["referee_note"]) for d in result.compare.doubtful_bars] == [(3, None)]


def test_a_low_confidence_ruling_stays_doubtful_with_the_referees_reason(ai_on, case, photo):
    score, reading, comparison = case

    def unsure(session, cancel):
        session.submit_ruling(2, "reader", "probably four beats", 0.4)

    result = run(score, reading, comparison, photo, agent_factory=stub_factory(unsure))
    [ruling] = result.referee["rulings"]
    assert ruling["rejected_because"] == "low_confidence"
    assert [(d["bar"], d["referee_note"]) for d in result.compare.doubtful_bars] == [
        (2, "probably four beats"), (3, None)]
    assert result.score.bars[1] == score.bars[1]


def test_a_homr_ruling_accepted_changes_no_notes_but_clears_the_bar(ai_on, photo):
    score = make_score([FOUR_QUARTERS, C5_QUARTERS])
    reading = make_reading({1: FOUR_QUARTERS, 2: D5_QUARTERS})
    comparison = compare_of(score, reading)

    def homr_wins(session, cancel):
        session.submit_ruling(2, "homr", "homr matches the photo", 0.8)

    result = run(score, reading, comparison, photo, agent_factory=stub_factory(homr_wins))
    assert result.score == score and result.compare.doubtful_bars == []


def test_ai_off_skips_and_leaves_everything_unchanged(monkeypatch, case, photo):
    monkeypatch.setattr(agent, "get_settings", lambda: SETTINGS_OFF)
    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(lambda s, c: pytest.fail("called")))
    assert (result.referee["status"], result.referee["reason"], result.referee["rulings"]) == ("skipped", "ai_off", [])
    assert result.score is score and result.compare is comparison


def test_bad_ai_settings_skip_as_ai_off(monkeypatch, case, photo):
    def broken():
        raise agent.ConfigError("AI_ENABLED is true but BEDROCK_VISION_MODEL is empty.")

    monkeypatch.setattr(agent, "get_settings", broken)
    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(lambda s, c: pytest.fail("called")))
    assert (result.referee["status"], result.referee["reason"]) == ("skipped", "ai_off")


def test_no_doubtful_bars_skips(ai_on, photo):
    score = make_score([FOUR_QUARTERS] * 3)
    reading = make_reading({n: FOUR_QUARTERS for n in (1, 2, 3)})
    comparison = compare_of(score, reading)
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(lambda s, c: pytest.fail("called")))
    assert (result.referee["status"], result.referee["reason"]) == ("skipped", "nothing_to_check")
    assert result.compare is comparison


def test_a_mostly_different_comparison_skips(ai_on, photo):
    score = make_score([FOUR_QUARTERS] * 3)
    reading = make_reading({n: D5_QUARTERS for n in (1, 2, 3)})
    comparison = compare_of(score, reading)
    assert comparison.warnings == [compare_module.MOSTLY_DIFFERENT_WARNING]
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(lambda s, c: pytest.fail("called")))
    assert (result.referee["status"], result.referee["reason"]) == ("skipped", "mostly_different")
    assert result.score is score and result.compare is comparison


def test_a_model_error_fails_the_referee_and_leaves_inputs_unchanged(ai_on, case, photo):
    def explode(session, cancel):
        raise RuntimeError("Bedrock is down")

    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(explode))
    assert (result.referee["status"], result.referee["reason"], result.referee["rulings"]) == ("failed", "model_error", [])
    assert result.score is score and result.compare is comparison


def test_a_factory_that_cannot_build_the_agent_is_a_model_error(ai_on, case, photo):
    def no_factory(settings, session, timeout_s):
        raise RuntimeError("no AWS credentials")

    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=no_factory)
    assert (result.referee["status"], result.referee["reason"]) == ("failed", "model_error")


def test_a_slow_model_times_out_and_is_cancelled(ai_on, case, photo):
    seen = {}

    def hang(session, cancel):
        seen["cancel"] = cancel
        cancel.wait(5)
        session.submit_ruling(2, "reader", "too late", 0.9)

    score, reading, comparison = case
    started = time.monotonic()
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(hang), timeout_s=1)
    assert time.monotonic() - started < 3
    assert (result.referee["status"], result.referee["reason"]) == ("failed", "timeout")
    assert seen["cancel"].is_set()
    time.sleep(0.2)  # the late ruling arrives after the run ended and changes nothing
    assert result.score is score and result.compare is comparison and result.referee["rulings"] == []


def test_a_ruling_accepted_before_a_failure_is_still_applied(ai_on, case, photo):
    def rule_then_explode(session, cancel):
        session.submit_ruling(2, "reader", "four beats", 0.9)
        raise RuntimeError("Bedrock dropped the connection")

    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(rule_then_explode))
    assert (result.referee["status"], result.referee["reason"]) == ("failed", "model_error")
    assert [r["bar"] for r in result.referee["rulings"]] == [2]
    assert [n.name for n in result.score.bars[1].notes] == ["D5"] * 4
    assert [d["bar"] for d in result.compare.doubtful_bars] == [3]


def test_a_ruling_accepted_before_a_timeout_is_still_applied(ai_on, case, photo):
    def rule_then_hang(session, cancel):
        session.submit_ruling(2, "reader", "four beats", 0.9)
        cancel.wait(5)

    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(rule_then_hang), timeout_s=0.5)
    assert result.referee["reason"] == "timeout"
    assert [d["bar"] for d in result.compare.doubtful_bars] == [3]


def test_a_reader_bar_that_cannot_be_converted_stays_doubtful_as_apply_failed(ai_on, case, photo, monkeypatch):
    def cannot_convert(bar, read_bar):
        raise apply.ApplyError("bar 2: cannot read the pitch 'H9'")

    monkeypatch.setattr(apply, "convert_reader_bar", cannot_convert)
    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(rule_bar_2_reader_and_bar_3_neither))
    assert result.referee["status"] == "done"
    assert result.referee["rulings"][0]["accepted"] is False
    assert result.referee["rulings"][0]["rejected_because"] == "apply_failed"
    assert [(d["bar"], d["referee_note"]) for d in result.compare.doubtful_bars] == [
        (2, "the reader counts four beats"), (3, "both look plausible")]
    assert result.score.bars[1] == score.bars[1]


def test_converting_unreadable_reader_notes_raises_apply_error(case):
    score, reading, comparison = case
    unreadable = make_reading({2: [("H9", "quarter")]}).bars[0]
    with pytest.raises(apply.ApplyError, match="pitch"):
        apply.convert_reader_bar(score.bars[1], unreadable)
    wobbly = make_reading({2: [("E5", "wobbly")]}).bars[0]
    with pytest.raises(apply.ApplyError, match="length"):
        apply.convert_reader_bar(score.bars[1], wobbly)


def test_applying_a_reader_bar_the_score_does_not_have_is_apply_failed(case):
    score, reading, comparison = case
    ruling = {"bar": 9, "pick": "reader", "why": "x", "confidence": 0.9, "accepted": True, "rejected_because": None}
    extra = make_reading({9: FOUR_QUARTERS}).bars[0]
    _, _, final = apply.apply_rulings(score, CompareResult(), [ruling], lambda bar: extra)
    assert final[0]["accepted"] is False and final[0]["rejected_because"] == "apply_failed"


def test_an_unexpected_crash_never_escapes(ai_on, case, photo, monkeypatch):
    def crash(*args, **kwargs):
        raise ValueError("bug")

    monkeypatch.setattr(agent, "RefereeSession", crash)
    score, reading, comparison = case
    result = run(score, reading, comparison, photo, agent_factory=stub_factory(lambda s, c: None))
    assert result.referee["status"] == "failed" and result.score is score and result.compare is comparison


def test_only_twenty_bars_are_refereed_and_the_rest_stay_doubtful(ai_on, photo):
    score = make_score([FOUR_QUARTERS] * 60)
    reading = make_reading({n: D5_QUARTERS if n <= 25 else FOUR_QUARTERS for n in range(1, 61)})
    comparison = compare_of(score, reading)

    def rule_everything(session, cancel):
        for entry in session.list_doubtful_bars():
            session.submit_ruling(entry["bar"], "reader", "x", 0.9)
        assert session.submit_ruling(21, "reader", "x", 0.9)["rejected_because"] == "unknown_bar"

    result = run(score, reading, comparison, photo, agent_factory=stub_factory(rule_everything))
    assert len(result.referee["rulings"]) == 20
    assert [d["bar"] for d in result.compare.doubtful_bars] == [21, 22, 23, 24, 25]
