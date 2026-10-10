import copy

import pytest

from app.agents.checker import check_plan


def exercise(**over):
    base = {
        "id": "e1",
        "title": "Fix bar 3 timing",
        "text": "Play bar 3 at 58 BPM, up 4 BPM per step to 70 BPM, 3 clean reps.",
        "bar_from": 3,
        "bar_to": 3,
        "start_bpm": 58,
        "target_bpm": 70,
        "step_bpm": 4,
        "reps_to_pass": 3,
        "pass_mark": {"max_errors": 0, "max_mean_timing_ms": 30, "form_rule": None},
        "problem_ids": ["p:t1:1"],
        "claims": [],
    }
    return {**base, **over}


WHOLE_RANGE = {
    "id": "e2",
    "text": "Play bars 1 to 4 from 60 BPM to 80 BPM in steps of 5, 2 clean reps.",
    "bar_from": 1,
    "bar_to": 4,
    "start_bpm": 60,
    "target_bpm": 80,
    "step_bpm": 5,
    "reps_to_pass": 2,
    "pass_mark": {"max_errors": 1, "max_mean_timing_ms": None, "form_rule": None},
    "problem_ids": ["p:t1:0"],
}


def whole_range(**over):
    return exercise(**{**WHOLE_RANGE, **over})


def plan(*exercises):
    return {"exercises": list(exercises)}


def reasons(result):
    return [p["reason"] for p in result["problems"]]


def assert_fails_with(result, prefix):
    assert not result["ok"]
    assert any(r.startswith(prefix) for r in reasons(result)), reasons(result)


def test_valid_plan_passes(check_ctx):
    result = check_plan(plan(exercise(), whole_range()), check_ctx)
    assert result == {"ok": True, "problems": [], "claims_checked": 0, "claims_failed": 0}


def test_start_too_fast_fails(check_ctx):
    fast = exercise(start_bpm=66, text="Play bar 3 at 66 BPM, up 4 BPM per step to 70 BPM, 3 clean reps.")
    assert_fails_with(check_plan(plan(fast, whole_range()), check_ctx), "start too fast")


def test_start_ceiling_without_clean_tempo_is_seventy_percent_of_target(check_ctx):
    check_ctx.history = []
    check_ctx.diagnosis = {**check_ctx.diagnosis, "error_rate": 0.4}
    ok = whole_range(start_bpm=58)
    ok["text"] = "Play bars 1 to 4 from 58 BPM to 80 BPM in steps of 5, 2 clean reps."
    assert check_plan(plan(exercise(start_bpm=50, text="Play bar 3 at 50 BPM, up 4 BPM per step to 70 BPM, 3 clean reps."), ok), check_ctx)["ok"]
    too_fast = {**ok, "start_bpm": 59, "text": ok["text"].replace("58", "59")}
    assert_fails_with(check_plan(plan(exercise(), too_fast), check_ctx), "start too fast")


def test_single_exercise_fails(check_ctx):
    assert_fails_with(check_plan(plan(exercise()), check_ctx), "bad exercise count")


def test_five_exercises_fail(check_ctx):
    assert_fails_with(check_plan(plan(*[exercise()] * 5), check_ctx), "bad exercise count")


def test_step_of_twelve_fails(check_ctx):
    big = exercise(step_bpm=12, text="Play bar 3 at 58 BPM, up 12 BPM per step to 70 BPM, 3 clean reps.")
    assert_fails_with(check_plan(plan(big, whole_range()), check_ctx), "bad step")


def test_bars_outside_range_fail(check_ctx):
    outside = exercise(bar_from=3, bar_to=9, text="Play bars 3 to 9 at 58 BPM, up 4 BPM per step to 70 BPM, 3 reps.")
    assert_fails_with(check_plan(plan(outside, whole_range()), check_ctx), "bars outside range")


def test_reversed_bars_fail(check_ctx):
    reversed_ = exercise(bar_from=4, bar_to=3, text="Play bars 4 to 3 at 58 BPM, up 4 BPM per step to 70 BPM, 3 reps.")
    assert_fails_with(check_plan(plan(reversed_, whole_range()), check_ctx), "bars outside range")


def test_problem_outside_exercise_bars_fails(check_ctx):
    assert_fails_with(check_plan(plan(exercise(problem_ids=["p:t1:0"]), whole_range()), check_ctx), "bars outside range: p:t1:0")


def test_unknown_problem_fails(check_ctx):
    assert_fails_with(check_plan(plan(exercise(problem_ids=["p:t1:77"]), whole_range()), check_ctx), "unknown id")


def test_note_id_is_not_a_problem(check_ctx):
    assert_fails_with(check_plan(plan(exercise(problem_ids=["n:t1:3:0"]), whole_range()), check_ctx), "unknown id")


@pytest.mark.parametrize("target", [75, 90])
def test_whole_range_target_must_equal_take_target(check_ctx, target):
    bad = whole_range()
    bad["target_bpm"] = target
    bad["text"] = f"Play bars 1 to 4 from 60 BPM to {target} BPM in steps of 5, 2 clean reps."
    assert_fails_with(check_plan(plan(exercise(), bad), check_ctx), "bad tempo")


def test_partial_range_target_cannot_exceed_take_target(check_ctx):
    bad = exercise(target_bpm=85, text="Play bar 3 at 58 BPM, up 4 BPM per step to 85 BPM, 3 clean reps.")
    assert_fails_with(check_plan(plan(bad, whole_range()), check_ctx), "bad tempo")


def test_start_below_thirty_fails(check_ctx):
    slow = exercise(start_bpm=20, text="Play bar 3 at 20 BPM, up 4 BPM per step to 70 BPM, 3 clean reps.")
    assert_fails_with(check_plan(plan(slow, whole_range()), check_ctx), "bad tempo")


@pytest.mark.parametrize("reps", [0, 6])
def test_reps_out_of_range_fail(check_ctx, reps):
    bad = exercise(reps_to_pass=reps, text=f"Play bar 3 at 58 BPM, up 4 BPM per step to 70 BPM, {reps} clean reps.")
    assert_fails_with(check_plan(plan(bad, whole_range()), check_ctx), "bad reps")


def test_max_errors_above_two_fails(check_ctx):
    bad = exercise(pass_mark={"max_errors": 3, "max_mean_timing_ms": None, "form_rule": None})
    assert_fails_with(check_plan(plan(bad, whole_range()), check_ctx), "bad pass mark")


def test_form_rule_must_be_flagged_in_take(check_ctx):
    mark = {"max_errors": 0, "max_mean_timing_ms": None}
    ok = exercise(pass_mark={**mark, "form_rule": "trumpet_head_down"}, bar_from=4, bar_to=4, problem_ids=["p:t1:2"],
                  text="Play bar 4 at 58 BPM, up 4 BPM per step to 70 BPM, 3 clean reps.")
    assert check_plan(plan(ok, whole_range()), check_ctx)["ok"]
    bad = copy.deepcopy(ok)
    bad["pass_mark"]["form_rule"] = "trumpet_elbows_pinned"
    assert_fails_with(check_plan(plan(bad, whole_range()), check_ctx), "bad pass mark")


def test_text_over_forty_words_fails(check_ctx):
    long = exercise(text="Play bar 3 " + "slowly " * 40)
    assert_fails_with(check_plan(plan(long, whole_range()), check_ctx), "text too long")


def test_stray_number_in_exercise_text_fails(check_ctx):
    stray = exercise(text="Play bar 3 at 58 BPM, up 4 BPM per step to 70 BPM, 9 clean reps.")
    assert_fails_with(check_plan(plan(stray, whole_range()), check_ctx), "stray number: 9")


def test_exercise_claims_are_checked(check_ctx):
    claims = [
        {"type": "timing_ms", "id": "p:t1:1", "field": None, "value": 88, "time_s": None},
        {"type": "direction", "id": "p:t1:1", "field": None, "value": "late", "time_s": None},
    ]
    good = exercise(text="Bar 3 is late by 88 ms: play it at 58 BPM, up 4 BPM per step to 70 BPM.", claims=claims)
    result = check_plan(plan(good, whole_range()), check_ctx)
    assert result["ok"] and result["claims_checked"] == 2
    bad_claims = [{**claims[0], "value": 130}, claims[1]]
    bad = exercise(text="Bar 3 is late by 130 ms: play it at 58 BPM, up 4 BPM per step to 70 BPM.", claims=bad_claims)
    result = check_plan(plan(bad, whole_range()), check_ctx)
    assert_fails_with(result, "timing mismatch")
    assert result["claims_failed"] == 1


def test_direction_word_in_exercise_needs_claim(check_ctx):
    bad = exercise(text="Bar 3 is late: play it at 58 BPM, up 4 BPM per step to 70 BPM.")
    assert_fails_with(check_plan(plan(bad, whole_range()), check_ctx), "unclaimed direction")


def test_malformed_plan_is_reported_not_raised(check_ctx):
    assert not check_plan(None, check_ctx)["ok"]
    assert not check_plan(plan("nonsense", {"bar_from": "x"}), check_ctx)["ok"]


@pytest.mark.parametrize(
    "over",
    [
        {"pass_mark": {"max_errors": 0, "max_mean_timing_ms": None, "form_rule": ["x"]}},
        {"pass_mark": {"max_errors": 0, "form_rule": {"a": 1}}},
        {"pass_mark": "easy"},
        {"pass_mark": {"max_errors": [0]}},
        {"pass_mark": None},
        {"problem_ids": [[1]]},
        {"problem_ids": "p:t1:1"},
        {"problem_ids": None},
        {"claims": "x"},
        {"claims": [None, 3, [1], {"type": "bar", "id": {"a": 1}, "value": 1}]},
        {"text": None},
        {"text": ["x"]},
        {"bar_from": [1]},
    ],
)
def test_malformed_exercise_is_rejected_not_raised(check_ctx, over):
    result = check_plan(plan(exercise(**over), whole_range()), check_ctx)
    assert not result["ok"]
    assert all(p["index"] == 0 for p in result["problems"])


def test_unexpected_failure_in_exercise_is_logged_and_rejected(check_ctx, caplog, monkeypatch):
    import app.agents.plan_rules as plan_rules

    def boom(*args):
        raise ValueError("unexpected")

    monkeypatch.setattr(plan_rules, "_check_bars", boom)
    result = check_plan(plan(exercise(), whole_range()), check_ctx)
    assert_fails_with(result, "bad exercise")
    assert "failed on malformed output" in caplog.text
