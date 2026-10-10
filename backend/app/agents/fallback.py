"""The rule-based feedback and practice plan used whenever the AI agents are off, failed or can't tell.

Plain functions, no model and no storage: a take's diagnosis in, sentences and exercises out.
Exercise ids are left to the caller, which owns the session's numbering.
"""
import logging
from dataclasses import dataclass

from app.agents.context import clean_tempo, item_bars
from app.agents.plan_rules import COLD_START_RATIO, MIN_START_BPM

log = logging.getLogger(__name__)

MAX_PROBLEM_EXERCISES = 3
STEP_BPM = 4
REPS_TO_PASS = 2
TIMING_MAX_MEAN_MS = 50
TIMING_KINDS = ("late", "early", "rushing", "dragging")
WHOLE_RANGE_MAX_ERRORS = 1
DEFAULT_BPM = 60
CANT_TELL_TEXT = "I couldn't tell how that went from this recording. Play it again slowly and clearly, and I'll listen once more."


@dataclass
class Fallback:
    sentences: list[dict]
    exercises: list[dict]
    cant_tell: bool


def target_bpm(diagnosis: dict, take: dict) -> float:
    for value in (diagnosis.get("target_bpm"), take.get("tempo_bpm"), diagnosis.get("played_bpm")):
        if isinstance(value, (int, float)) and value > 0:
            return value
    log.warning("take %s has no tempo; using %s BPM", take.get("take_id"), DEFAULT_BPM)
    return DEFAULT_BPM


def bar_range(diagnosis: dict, take: dict) -> tuple[int, int]:
    """The bars the Checker will accept: the diagnosed bars, else the bars the take was recorded on."""
    bars = [b["bar"] for b in diagnosis.get("bars") or []]
    return (min(bars), max(bars)) if bars else (take["bar_from"], take["bar_to"])


def _cold_start_bpm(target: float) -> int:
    return max(MIN_START_BPM, int(COLD_START_RATIO * target))


def _start_bpm(diagnosis: dict, history: list[dict], target: float) -> int:
    """The clean tempo (never above the target), else 70% of the target."""
    own = {"error_rate": diagnosis.get("error_rate"), "played_bpm": diagnosis.get("played_bpm")}
    clean = clean_tempo(history, own)
    return int(min(clean, target)) if clean is not None else _cold_start_bpm(target)


def _text(bar_from: int, bar_to: int, start: int, step: int, reps: int, target: float) -> str:
    where = f"bar {bar_from}" if bar_from == bar_to else f"bars {bar_from} to {bar_to}"
    return (f"Play {where} at {start} BPM. Once you play it cleanly {reps} times in a row, "
            f"add {step} BPM. Keep going until you reach {target:g} BPM.")


def _exercise(title: str, bars: tuple[int, int], start: int, target: float, pass_mark: dict, problem_ids: list[str]) -> dict:
    return {
        "title": title, "text": _text(*bars, start, STEP_BPM, REPS_TO_PASS, target),
        "bar_from": bars[0], "bar_to": bars[1], "start_bpm": start, "target_bpm": target,
        "step_bpm": STEP_BPM, "reps_to_pass": REPS_TO_PASS, "pass_mark": pass_mark,
        "problem_ids": problem_ids, "claims": [],
    }


def _pass_mark(max_errors: int) -> dict:
    return {"max_errors": max_errors, "max_mean_timing_ms": None, "form_rule": None}


def _problem_pass_mark(problem: dict, form_flags: dict[str, dict]) -> dict:
    mark = _pass_mark(0)
    if problem.get("kind") in TIMING_KINDS:
        mark["max_mean_timing_ms"] = TIMING_MAX_MEAN_MS
    elif problem.get("kind") == "form":
        rules = [form_flags[i]["rule"] for i in problem.get("measurement_ids") or [] if i in form_flags]
        mark["form_rule"] = rules[0] if rules else None
    return mark


def _tier1_problems(diagnosis: dict) -> list[dict]:
    problems = [p for p in diagnosis.get("problems") or [] if p.get("tier") == 1]
    return sorted(problems, key=lambda p: p.get("score", 0), reverse=True)[:MAX_PROBLEM_EXERCISES]


def _sentence(item: dict, problems: dict[str, dict]) -> dict:
    cited = [problems[i] for i in item.get("cites") or [] if i in problems]
    bars = item_bars(cited[0]) if cited else []
    return {"text": item["text"], "cites": item.get("cites") or [], "claims": [],
            "jump": {"bar": bars[0] if bars else None, "time_s": None}, "checked": True, "mode": "fallback"}


def tier1_sentences(diagnosis: dict) -> list[dict]:
    problems = {p["id"]: p for p in diagnosis.get("problems") or []}
    return [_sentence(item, problems) for item in diagnosis.get("tier1") or []]


def _retake_exercise(bars: tuple[int, int], target: float) -> dict:
    return _exercise("Play it again, slowly", bars, _cold_start_bpm(target),
                     target, _pass_mark(WHOLE_RANGE_MAX_ERRORS), [])


def build_fallback(diagnosis: dict, take: dict, history: list[dict], form_flags: dict[str, dict]) -> Fallback:
    """Tier 1 sentences and a rule plan, or, for a take that can't be judged, the can't-tell message and a retake."""
    bars, target = bar_range(diagnosis, take), target_bpm(diagnosis, take)
    if diagnosis.get("cant_tell"):
        sentence = {"text": CANT_TELL_TEXT, "cites": [], "claims": [], "jump": {"bar": None, "time_s": None},
                    "checked": True, "mode": "fallback"}
        return Fallback([sentence], [_retake_exercise(bars, target)], cant_tell=True)
    start = _start_bpm(diagnosis, history, target)
    problems = _tier1_problems(diagnosis)
    exercises = []
    for problem in problems:
        problem_bars = item_bars(problem)
        span = (min(problem_bars), max(problem_bars)) if problem_bars else bars
        exercises.append(_exercise(f"Work on bars {span[0]} to {span[1]}", span, start, target,
                                   _problem_pass_mark(problem, form_flags), [problem["id"]]))
    exercises.append(_exercise("Put it together", bars, start, target,
                               _pass_mark(WHOLE_RANGE_MAX_ERRORS), [p["id"] for p in problems]))
    return Fallback(tier1_sentences(diagnosis), exercises, cant_tell=False)
