"""The practice loop's rules: whether a rep passes the exercise's pass mark, and how the tempo ladder moves.

Pure functions on plain dicts: no I/O and no store. Exercises are the plan's exercises (with a nested `pass_mark`),
diagnoses are saved diagnoses, flags are form flags, and an exercise state is
{current_bpm, streak, fails_in_row, best_passed_bpm, complete, ...}.
"""
from statistics import mean
from typing import Any

from ..diagnosis.config import STATUS_MISSED, STATUS_WRONG, TIMED_STATUSES

ERROR_STATUSES = (STATUS_WRONG, STATUS_MISSED)

VIDEO_KIND = "video"
FORM_DONE = "done"
FORM_NOT_CHECKED_REASON = "form not checked"
FAILS_IN_ROW_TO_STEP_DOWN = 2
SECONDS_PER_MINUTE = 60


def _in_bars(item: dict, exercise: dict) -> bool:
    return exercise["bar_from"] <= item["bar"] <= exercise["bar_to"]


def _count_errors(exercise: dict, diagnosis: dict) -> int:
    notes = [n for n in diagnosis["notes"] if _in_bars(n, exercise)]
    extras = [x for x in diagnosis.get("extras") or [] if _in_bars(x, exercise)]
    return sum(1 for n in notes if n["status"] in ERROR_STATUSES) + len(extras)


def _mean_abs_timing_ms(exercise: dict, diagnosis: dict) -> float | None:
    timings = [abs(n["timing_ms"]) for n in diagnosis["notes"]
               if _in_bars(n, exercise) and n["status"] in TIMED_STATUSES and n.get("timing_ms") is not None]
    return mean(timings) if timings else None


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // SECONDS_PER_MINUTE}:{whole % SECONDS_PER_MINUTE:02d}"


def _errors_reason(errors: int, max_errors: int) -> str:
    return f"{errors} {'error' if errors == 1 else 'errors'}, pass mark {max_errors}"


def judge_rep(exercise: dict, diagnosis: dict, take_kind: str, form_status: str, form_flags: list[dict[str, Any]]) -> dict:
    """Judge one rep against the exercise's pass mark.

    Returns {passed, reasons, errors, mean_abs_timing_ms, form_flag_ids}; `reasons` lists each failed mark with its number
    and the pass mark, plus 'form not checked' when the mark has a form rule that couldn't be checked.
    A can't-tell or failed take is the caller's to handle: don't judge it.
    """
    pass_mark = exercise["pass_mark"]
    errors = _count_errors(exercise, diagnosis)
    mean_timing = _mean_abs_timing_ms(exercise, diagnosis)
    reasons: list[str] = []
    passed = True

    if errors > pass_mark["max_errors"]:
        passed = False
        reasons.append(_errors_reason(errors, pass_mark["max_errors"]))

    max_timing = pass_mark.get("max_mean_timing_ms")
    if max_timing is not None and mean_timing is not None and mean_timing > max_timing:
        passed = False
        reasons.append(f"mean timing {mean_timing:.0f} ms, pass mark {max_timing:g} ms")

    flags: list[dict[str, Any]] = []
    form_rule = pass_mark.get("form_rule")
    if form_rule:
        if take_kind == VIDEO_KIND and form_status == FORM_DONE:
            flags = [f for f in form_flags if f["rule"] == form_rule]
            if flags:
                passed = False
                reasons.extend(f"{f['label']} at {_clock(f['start_s'])}" for f in flags)
        else:
            reasons.append(FORM_NOT_CHECKED_REASON)

    return {"passed": passed, "reasons": reasons, "errors": errors, "mean_abs_timing_ms": mean_timing,
            "form_flag_ids": [f["id"] for f in flags]}


def step_ladder(state: dict, exercise: dict, passed: bool) -> dict:
    """The exercise state after one counted rep (a copy; `state` isn't changed).

    A pass extends the streak and, at reps_to_pass, steps the tempo up (or completes the exercise at the target).
    A fail resets the streak and, on the second fail in a row, steps the tempo down. The new tempo is `current_bpm`.
    """
    new = dict(state)
    if passed:
        new["streak"] = state["streak"] + 1
        new["fails_in_row"] = 0
        new["best_passed_bpm"] = max(state["best_passed_bpm"] or 0, state["current_bpm"])
        if new["streak"] >= exercise["reps_to_pass"]:
            if state["current_bpm"] >= exercise["target_bpm"]:
                new["complete"] = True
            else:
                new["current_bpm"] = min(exercise["target_bpm"], state["current_bpm"] + exercise["step_bpm"])
                new["streak"] = 0
    else:
        new["streak"] = 0
        new["fails_in_row"] = state["fails_in_row"] + 1
        if new["fails_in_row"] >= FAILS_IN_ROW_TO_STEP_DOWN:
            new["current_bpm"] = max(exercise["start_bpm"], state["current_bpm"] - exercise["step_bpm"])
            new["fails_in_row"] = 0
    return new
