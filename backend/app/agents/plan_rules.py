"""Checker rules for a practice plan: exercise limits, tempos and pass marks."""
from typing import Any

from app.agents.claims import check_claim, check_text, is_number
from app.agents.context import CheckContext, item_bars, item_kind
from app.agents.report import Report

EXERCISE_COUNT = (2, 4)
EXERCISE_WORDS_MAX = 40
MIN_START_BPM = 30
STEP_BPM = (2, 10)
REPS_TO_PASS = (1, 5)
MAX_ERRORS = (0, 2)
START_ABOVE_CLEAN_BPM = 2
COLD_START_RATIO = 0.7
_REQUIRED_NUMBERS = ("bar_from", "bar_to", "start_bpm", "target_bpm", "step_bpm", "reps_to_pass")


def _in_range(value: float, bounds: tuple[int, int]) -> bool:
    return bounds[0] <= value <= bounds[1]


def _check_bars(index: int, ex: dict, ctx: CheckContext, report: Report) -> None:
    bounds = ctx.bar_range
    if bounds is None:
        report.add(index, "no bar range: the take has no bars to practise")
        return
    if ex["bar_from"] > ex["bar_to"] or not (_in_range(ex["bar_from"], bounds) and _in_range(ex["bar_to"], bounds)):
        report.add(index, f"bars outside range: {ex['bar_from']}-{ex['bar_to']} not within take bars {bounds[0]}-{bounds[1]}")


def _check_tempos(index: int, ex: dict, ctx: CheckContext, report: Report) -> None:
    start, target = ex["start_bpm"], ex["target_bpm"]
    if start < MIN_START_BPM or start > target:
        report.add(index, f"bad tempo: start {start} BPM must be {MIN_START_BPM} to target {target} BPM")
    take_target = ctx.target_bpm
    if is_number(take_target):
        whole_range = ctx.bar_range == (ex["bar_from"], ex["bar_to"])
        if (whole_range and target != take_target) or target > take_target:
            report.add(index, f"bad tempo: target {target} BPM does not fit the take's target {take_target} BPM")
    clean = ctx.clean_bpm
    ceiling = clean + START_ABOVE_CLEAN_BPM if clean is not None else COLD_START_RATIO * target + START_ABOVE_CLEAN_BPM
    if start > ceiling:
        report.add(index, f"start too fast: {start} BPM is above {ceiling:g} BPM ({'clean tempo' if clean is not None else '70% of target'} + 2)")
    if not _in_range(ex["step_bpm"], STEP_BPM):
        report.add(index, f"bad step: {ex['step_bpm']} BPM is outside {STEP_BPM[0]}-{STEP_BPM[1]}")
    if not _in_range(ex["reps_to_pass"], REPS_TO_PASS):
        report.add(index, f"bad reps: {ex['reps_to_pass']} is outside {REPS_TO_PASS[0]}-{REPS_TO_PASS[1]}")


def _check_pass_mark(index: int, ex: dict, ctx: CheckContext, report: Report) -> None:
    mark = ex.get("pass_mark")
    if not isinstance(mark, dict) or not is_number(mark.get("max_errors")):
        report.add(index, "bad pass mark: needs max_errors")
        return
    if not _in_range(mark["max_errors"], MAX_ERRORS):
        report.add(index, f"bad pass mark: max_errors {mark['max_errors']} is outside {MAX_ERRORS[0]}-{MAX_ERRORS[1]}")
    max_timing = mark.get("max_mean_timing_ms")
    if max_timing is not None and (not is_number(max_timing) or max_timing < 0):
        report.add(index, "bad pass mark: max_mean_timing_ms must be a positive number or null")
    rule = mark.get("form_rule")
    if rule is not None and not (isinstance(rule, str) and rule in ctx.flag_rules):
        report.add(index, f"bad pass mark: form rule {rule} was not flagged in this take")


def _check_problems(index: int, ex: dict, ctx: CheckContext, report: Report) -> None:
    problem_ids = ex.get("problem_ids")
    if not isinstance(problem_ids, list) or not problem_ids:
        report.add(index, "uncited: exercise has no problem_ids")
        return
    for problem_id in problem_ids:
        item = ctx.find(problem_id)
        if item is None or item_kind(problem_id) != "problem":
            report.add(index, f"unknown id: {problem_id} is not a problem of this take")
        elif any(not ex["bar_from"] <= bar <= ex["bar_to"] for bar in item_bars(item)):
            report.add(index, f"bars outside range: {problem_id} lies in bars {item_bars(item)}, outside {ex['bar_from']}-{ex['bar_to']}")


def _check_text_and_claims(index: int, ex: dict, ctx: CheckContext, report: Report) -> None:
    text = ex.get("text")
    if not isinstance(text, str) or not text.strip():
        report.add(index, "bad text: exercise needs text")
        return
    if len(text.split()) > EXERCISE_WORDS_MAX:
        report.add(index, f"text too long: more than {EXERCISE_WORDS_MAX} words")
    claims = [c for c in ex.get("claims") or [] if isinstance(c, dict)]
    for claim in ex.get("claims") or []:
        report.claims_checked += 1
        reason = check_claim(claim, ctx)
        if reason:
            report.add(index, reason, claim)
    mark = ex["pass_mark"] if isinstance(ex.get("pass_mark"), dict) else {}
    own_numbers = [ex.get(k) for k in _REQUIRED_NUMBERS] + [mark.get("max_errors"), mark.get("max_mean_timing_ms")]
    cited_bars = [b for pid in ex.get("problem_ids") or [] for b in item_bars(ctx.find(pid) or {})]
    for reason in check_text(text, claims, [n for n in own_numbers if is_number(n)] + cited_bars):
        report.add(index, reason)


def check_exercise(index: int, ex: Any, ctx: CheckContext, report: Report) -> None:
    if not isinstance(ex, dict) or not all(is_number(ex.get(k)) for k in _REQUIRED_NUMBERS):
        report.add(index, "bad exercise: bar_from, bar_to, start_bpm, target_bpm, step_bpm and reps_to_pass must be numbers")
        return
    for name in ("problem_ids", "claims"):
        if ex.get(name) is not None and not isinstance(ex[name], list):
            report.add(index, f"bad exercise: {name} must be a list")
            return
    _check_bars(index, ex, ctx, report)
    _check_tempos(index, ex, ctx, report)
    _check_pass_mark(index, ex, ctx, report)
    _check_problems(index, ex, ctx, report)
    _check_text_and_claims(index, ex, ctx, report)
