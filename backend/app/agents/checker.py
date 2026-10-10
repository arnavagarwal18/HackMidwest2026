"""The Checker: verifies Coach feedback and Planner output against the stored diagnosis.

Plain Python, no model. Every claim is recomputed from the stored measurement it names;
anything that does not hold is reported with a reason the Coach or Planner can act on.
"""
from typing import Any

from app.agents.claims import FORM_TIME_MARGIN_S, check_claim, check_text, is_number
from app.agents.context import CheckContext, item_bars, item_kind
from app.agents.plan_rules import EXERCISE_COUNT, check_exercise
from app.agents.report import Report

SENTENCE_COUNT = (1, 6)
SENTENCE_WORDS_MAX = 30
PROBLEM_COUNT = (1, 3)


def _bars_cited(sentence: dict, ctx: CheckContext) -> set[int]:
    ids = [*sentence.get("cites", []), *[c.get("id") for c in sentence.get("claims", []) if isinstance(c, dict)]]
    bars = {b for item_id in ids for b in item_bars(ctx.find(item_id) or {})}
    bars |= {c["value"] for c in sentence.get("claims", []) if isinstance(c, dict) and c.get("type") == "bar" and is_number(c.get("value"))}
    return bars


def _check_jump(sentence: dict, ctx: CheckContext) -> list[str]:
    """Rule e: the jump points at a cited bar or at a flag's time."""
    jump = sentence.get("jump") or {}
    reasons = []
    bar, time_s = jump.get("bar"), jump.get("time_s")
    if bar is not None and not (is_number(bar) and bar in _bars_cited(sentence, ctx)):
        reasons.append(f"bad jump: bar {bar} is not a cited bar")
    if time_s is not None and not (
        is_number(time_s)
        and any(f["start_s"] - FORM_TIME_MARGIN_S <= time_s <= f["end_s"] + FORM_TIME_MARGIN_S for f in ctx.form_flags)
    ):
        reasons.append(f"bad jump: time {time_s} is not inside any form flag")
    return reasons


def _check_ids(sentence: dict, ctx: CheckContext) -> list[str]:
    """Rules a and d: cited and claimed ids exist, and none is an uncertain note."""
    cites = sentence.get("cites")
    if not isinstance(cites, list) or not cites:
        return ["uncited: a sentence must cite at least one measurement id"]
    claimed = [c.get("id") for c in sentence.get("claims", []) if isinstance(c, dict)]
    reasons = []
    seen = []
    for item_id in [*cites, *claimed]:
        if item_id in seen:
            continue
        seen.append(item_id)
        item = ctx.find(item_id)
        if item is None:
            reasons.append(f"unknown id: {item_id}")
        elif item_kind(item_id) == "note" and item.get("status") == "uncertain":
            reasons.append(f"uncertain note: {item_id} is too uncertain to cite")
    return reasons


def check_sentence(index: int, sentence: Any, ctx: CheckContext, report: Report) -> None:
    if not isinstance(sentence, dict) or not isinstance(sentence.get("text"), str):
        report.add(index, "bad sentence: needs text, cites, claims and jump")
        return
    for name, expected in (("cites", list), ("claims", list), ("jump", dict)):
        if sentence.get(name) is not None and not isinstance(sentence[name], expected):
            report.add(index, f"bad sentence: {name} must be a {expected.__name__}")
            return
    sentence = {**sentence, "cites": sentence.get("cites") or [], "claims": sentence.get("claims") or [], "jump": sentence.get("jump") or {}}
    for reason in _check_ids(sentence, ctx):
        report.add(index, reason)
    if len(sentence["text"].split()) > SENTENCE_WORDS_MAX:
        report.add(index, f"text too long: more than {SENTENCE_WORDS_MAX} words")
    raw_claims = sentence.get("claims") or []
    for claim in raw_claims:
        report.claims_checked += 1
        reason = check_claim(claim, ctx)
        # An unknown claimed id is already reported once by the id check.
        if reason and not reason.startswith("unknown id"):
            report.add(index, reason, claim)
    claims = [c for c in raw_claims if isinstance(c, dict)]
    jump = sentence.get("jump") or {}
    jump_numbers = [jump[k] for k in ("bar", "time_s") if is_number(jump.get(k))]
    allowed = [*_bars_cited(sentence, ctx), *jump_numbers]
    for reason in check_text(sentence["text"], claims, allowed):
        report.add(index, reason)
    for reason in _check_jump(sentence, ctx):
        report.add(index, reason)


def check_feedback(output: Any, ctx: CheckContext) -> dict:
    """Check CoachOutput { sentences, problem_ids }.

    Returns { ok, problems: [{ index, claim, reason }], claims_checked, claims_failed }.
    """
    report = Report()
    if not isinstance(output, dict):
        report.add(None, "bad output: expected { sentences, problem_ids }")
        return report.as_result()
    sentences = output.get("sentences")
    if not isinstance(sentences, list) or not SENTENCE_COUNT[0] <= len(sentences) <= SENTENCE_COUNT[1]:
        report.add(None, f"bad sentence count: need {SENTENCE_COUNT[0]} to {SENTENCE_COUNT[1]} sentences")
        sentences = sentences if isinstance(sentences, list) else []
    problem_ids = output.get("problem_ids")
    if not isinstance(problem_ids, list) or not PROBLEM_COUNT[0] <= len(problem_ids) <= PROBLEM_COUNT[1]:
        report.add(None, f"bad problem count: need {PROBLEM_COUNT[0]} to {PROBLEM_COUNT[1]} problem_ids")
    else:
        for problem_id in problem_ids:
            if item_kind(problem_id) != "problem" or ctx.find(problem_id) is None:
                report.add(None, f"unknown id: {problem_id} is not a problem of this take")
    for index, sentence in enumerate(sentences):
        with report.guard(index, "sentence"):
            check_sentence(index, sentence, ctx, report)
    return report.as_result()


def check_plan(output: Any, ctx: CheckContext) -> dict:
    """Check PlannerOutput { exercises }.

    Returns { ok, problems: [{ index, claim, reason }], claims_checked, claims_failed }.
    """
    report = Report()
    exercises = output.get("exercises") if isinstance(output, dict) else None
    if not isinstance(exercises, list) or not EXERCISE_COUNT[0] <= len(exercises) <= EXERCISE_COUNT[1]:
        report.add(None, f"bad exercise count: need {EXERCISE_COUNT[0]} to {EXERCISE_COUNT[1]} exercises")
        exercises = exercises if isinstance(exercises, list) else []
    for index, exercise in enumerate(exercises):
        with report.guard(index, "exercise"):
            check_exercise(index, exercise, ctx, report)
    return report.as_result()
