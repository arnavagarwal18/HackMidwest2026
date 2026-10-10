from app.practice.rules import judge_rep, step_ladder

EXERCISE = {
    "bar_from": 2, "bar_to": 3, "start_bpm": 60, "target_bpm": 72, "step_bpm": 4, "reps_to_pass": 2,
    "pass_mark": {"max_errors": 0, "max_mean_timing_ms": None, "form_rule": None},
}


def exercise(**pass_mark):
    return {**EXERCISE, "pass_mark": {**EXERCISE["pass_mark"], **pass_mark}}


def note(bar, status="ok", timing_ms=0.0):
    return {"id": f"n{bar}{status}", "bar": bar, "status": status, "timing_ms": timing_ms}


def diagnosis(*notes, extras=()):
    return {"notes": list(notes), "extras": list(extras), "cant_tell": False}


def judge(ex, diag, kind="mic", form_status="none", flags=()):
    return judge_rep(ex, diag, kind, form_status, list(flags))


def test_clean_rep_passes():
    result = judge(EXERCISE, diagnosis(note(2), note(3)))
    assert result == {"passed": True, "reasons": [], "errors": 0, "mean_abs_timing_ms": 0, "form_flag_ids": []}


def test_one_error_fails_with_singular_reason():
    result = judge(EXERCISE, diagnosis(note(2), note(3, "wrong", None)))
    assert not result["passed"]
    assert result["reasons"] == ["1 error, pass mark 0"]


def test_wrong_missed_and_extra_all_count_as_errors():
    result = judge(exercise(max_errors=5), diagnosis(note(2, "wrong"), note(3, "missed", None), extras=[{"id": "x1", "bar": 2}]))
    assert result["errors"] == 3
    assert result["passed"]


def test_too_many_errors_reason_is_plural():
    result = judge(EXERCISE, diagnosis(note(2, "wrong"), note(3, "missed", None)))
    assert result["reasons"] == ["2 errors, pass mark 0"]


def test_errors_within_max_errors_pass():
    assert judge(exercise(max_errors=1), diagnosis(note(2, "wrong")))["passed"]


def test_uncertain_note_is_not_an_error():
    result = judge(EXERCISE, diagnosis(note(2), note(3, "uncertain", None)))
    assert result["passed"] and result["errors"] == 0


def test_notes_and_extras_outside_the_bars_are_ignored():
    result = judge(EXERCISE, diagnosis(note(1, "wrong", 500), note(4, "missed", None), note(2), extras=[{"id": "x", "bar": 9}]))
    assert result["passed"] and result["errors"] == 0 and result["mean_abs_timing_ms"] == 0


def test_mean_timing_over_the_mark_fails():
    result = judge(exercise(max_mean_timing_ms=50), diagnosis(note(2, timing_ms=72), note(3, timing_ms=-72)))
    assert result["mean_abs_timing_ms"] == 72
    assert not result["passed"]
    assert result["reasons"] == ["mean timing 72 ms, pass mark 50 ms"]


def test_mean_timing_averages_ok_and_wrong_notes_only():
    diag = diagnosis(note(2, timing_ms=40), note(2, "wrong", -60), note(3, "uncertain", 900), note(3, "missed", None))
    assert judge(exercise(max_errors=9), diag)["mean_abs_timing_ms"] == 50


def test_no_timed_notes_gives_null_mean_and_passes_the_timing_mark():
    result = judge(exercise(max_errors=9, max_mean_timing_ms=50), diagnosis(note(2, "missed", None)))
    assert result["mean_abs_timing_ms"] is None and result["passed"]


def test_form_rule_with_matching_flag_fails():
    flags = [{"id": "f:t1:0", "rule": "bow_elbow", "label": "bow elbow too low", "start_s": 4.7},
             {"id": "f:t1:1", "rule": "other", "label": "other", "start_s": 9}]
    result = judge(exercise(form_rule="bow_elbow"), diagnosis(note(2)), "video", "done", flags)
    assert not result["passed"]
    assert result["reasons"] == ["bow elbow too low at 0:04"]
    assert result["form_flag_ids"] == ["f:t1:0"]


def test_form_rule_with_no_matching_flag_passes():
    flags = [{"id": "f:t1:1", "rule": "other", "label": "other", "start_s": 9}]
    result = judge(exercise(form_rule="bow_elbow"), diagnosis(note(2)), "video", "done", flags)
    assert result["passed"] and result["reasons"] == [] and result["form_flag_ids"] == []


def test_form_flag_time_is_minutes_and_seconds():
    flags = [{"id": "f:t1:0", "rule": "r", "label": "shoulders raised", "start_s": 75}]
    assert judge(exercise(form_rule="r"), diagnosis(note(2)), "video", "done", flags)["reasons"] == ["shoulders raised at 1:15"]


def test_form_rule_on_mic_rep_judges_notes_only():
    flags = [{"id": "f:t1:0", "rule": "r", "label": "x", "start_s": 1}]
    result = judge(exercise(form_rule="r"), diagnosis(note(2)), "mic", "done", flags)
    assert result["passed"] and result["reasons"] == ["form not checked"] and result["form_flag_ids"] == []


def test_form_rule_on_video_without_finished_form_judges_notes_only():
    for status in ("none", "processing", "failed"):
        result = judge(exercise(form_rule="r"), diagnosis(note(2)), "video", status)
        assert result["passed"] and result["reasons"] == ["form not checked"]


def test_form_not_checked_comes_after_failed_note_marks():
    result = judge(exercise(form_rule="r"), diagnosis(note(2, "wrong")), "mic")
    assert not result["passed"]
    assert result["reasons"] == ["1 error, pass mark 0", "form not checked"]


def state(current_bpm=60, streak=0, fails_in_row=0, best_passed_bpm=None, complete=False):
    return {"current_bpm": current_bpm, "streak": streak, "fails_in_row": fails_in_row,
            "best_passed_bpm": best_passed_bpm, "complete": complete, "reps": 4}


def test_two_passes_step_up():
    first = step_ladder(state(), EXERCISE, True)
    assert first == state(60, 1, 0, 60) | {"reps": 4}
    second = step_ladder(first, EXERCISE, True)
    assert second["current_bpm"] == 64 and second["streak"] == 0 and second["best_passed_bpm"] == 60


def test_best_passed_keeps_the_highest_tempo():
    assert step_ladder(state(60, best_passed_bpm=68), EXERCISE, True)["best_passed_bpm"] == 68


def test_step_ladder_returns_a_copy():
    before = state()
    step_ladder(before, EXERCISE, True)
    assert before == state()


def test_a_fail_resets_the_streak_and_counts_the_fail():
    result = step_ladder(state(64, streak=1, best_passed_bpm=60), EXERCISE, False)
    assert result["streak"] == 0 and result["fails_in_row"] == 1 and result["current_bpm"] == 64


def test_two_fails_in_a_row_step_down():
    once = step_ladder(state(64), EXERCISE, False)
    twice = step_ladder(once, EXERCISE, False)
    assert twice["current_bpm"] == 60 and twice["fails_in_row"] == 0


def test_a_pass_resets_fails_in_row():
    assert step_ladder(state(64, fails_in_row=1), EXERCISE, True)["fails_in_row"] == 0


def test_tempo_never_goes_below_start():
    assert step_ladder(state(60, fails_in_row=1), EXERCISE, False)["current_bpm"] == 60


def test_tempo_never_goes_above_target():
    ex = {**EXERCISE, "step_bpm": 8}
    assert step_ladder(state(68, streak=1), ex, True)["current_bpm"] == 72


def test_two_passes_at_the_target_complete_the_exercise():
    first = step_ladder(state(72), EXERCISE, True)
    assert not first["complete"]
    second = step_ladder(first, EXERCISE, True)
    assert second["complete"] and second["current_bpm"] == 72 and second["best_passed_bpm"] == 72
