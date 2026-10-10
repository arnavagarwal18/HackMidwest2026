"""Step 7: problems per bar (notes, late / early, rushing / dragging), merged across adjacent bars, plus form flags."""
import logging
from dataclasses import dataclass
from statistics import mean

from . import config
from .timing import drift_label, timing_flag

logger = logging.getLogger("app.diagnosis")

NO_CONFIDENCE_CERTAINTY = 1.0  # a problem made only of missed notes has no note confidence to average


@dataclass
class BarProblem:
    """One kind of problem in one bar, before merging with its neighbours."""

    kind: str
    bar: int
    first_time_s: float
    measurement_ids: list[str]
    size: float
    confidences: list[float]
    numbers: dict


def _round(value: float) -> float:
    return round(value, config.RANK_DECIMALS)


def _notes_problem(bar: dict, notes: list[dict], extras: list[dict]) -> BarProblem | None:
    wrong = [n for n in notes if n["status"] == config.STATUS_WRONG]
    missed = [n for n in notes if n["status"] == config.STATUS_MISSED]
    count = len(wrong) + len(missed) + len(extras)
    if count < 1:
        return None
    numbers = {"wrong": len(wrong), "missed": len(missed), "extra": len(extras)}
    if wrong:
        numbers["first_wrong"] = {"played": wrong[0]["played_name"], "expected": wrong[0]["expected_name"]}
    times = [n["expected_onset_s"] for n in wrong + missed] + [x["onset_s"] for x in extras]
    return BarProblem(
        kind=config.PROBLEM_NOTES,
        bar=bar["bar"],
        first_time_s=min(times),
        measurement_ids=[n["id"] for n in wrong + missed] + [x["id"] for x in extras],
        size=min(1.0, count / bar["expected"]) if bar["expected"] else 1.0,
        confidences=[n["confidence"] for n in wrong] + [x["confidence"] for x in extras],
        numbers=numbers,
    )


def _timing_problem(kind: str, bar: dict, notes: list[dict]) -> BarProblem | None:
    flagged = [n for n in notes if timing_flag(n["timing_ms"]) == kind]
    if len(flagged) < config.MIN_TIMED_NOTES_FOR_TIMING_PROBLEM:
        return None
    mean_ms = abs(mean(n["timing_ms"] for n in flagged))
    return BarProblem(
        kind=kind,
        bar=bar["bar"],
        first_time_s=min(n["expected_onset_s"] for n in flagged),
        measurement_ids=[n["id"] for n in flagged],
        size=min(1.0, mean_ms / config.TIMING_SIZE_FULL_MS),
        confidences=[n["confidence"] for n in flagged],
        numbers={"mean_ms": mean_ms, "count": len(flagged)},
    )


def _drift_problem(bar: dict, notes: list[dict], target_bpm: float) -> BarProblem | None:
    kind = drift_label(bar["drift_pct"])
    if kind not in (config.DRIFT_RUSHING, config.DRIFT_DRAGGING):
        return None
    ok_notes = [n for n in notes if n["status"] == config.STATUS_OK]
    return BarProblem(
        kind=kind,
        bar=bar["bar"],
        first_time_s=min(n["expected_onset_s"] for n in notes),
        measurement_ids=[bar["id"]],
        size=min(1.0, abs(bar["drift_pct"]) / config.DRIFT_SIZE_FULL_PCT),
        confidences=[n["confidence"] for n in ok_notes],
        numbers={"drift_pct": abs(bar["drift_pct"]), "target_bpm": target_bpm},
    )


def bar_problems(diagnosis: dict) -> list[BarProblem]:
    """Every per-bar problem in bar order."""
    found = []
    for bar in diagnosis["bars"]:
        notes = [n for n in diagnosis["notes"] if n["bar"] == bar["bar"]]
        extras = [x for x in diagnosis["extras"] if x["bar"] == bar["bar"]]
        candidates = [
            _notes_problem(bar, notes, extras),
            _timing_problem(config.TIMING_LATE, bar, notes),
            _timing_problem(config.TIMING_EARLY, bar, notes),
            _drift_problem(bar, notes, diagnosis["target_bpm"]),
        ]
        found.extend(problem for problem in candidates if problem is not None)
    return found


def _merged_numbers(kind: str, parts: list[BarProblem]) -> dict:
    if kind == config.PROBLEM_NOTES:
        numbers = {key: sum(p.numbers[key] for p in parts) for key in ("wrong", "missed", "extra")}
        first_wrong = next((p.numbers["first_wrong"] for p in parts if "first_wrong" in p.numbers), None)
        return {**numbers, **({"first_wrong": first_wrong} if first_wrong else {})}
    if kind in (config.TIMING_LATE, config.TIMING_EARLY):
        count = sum(p.numbers["count"] for p in parts)
        weighted = sum(p.numbers["mean_ms"] * p.numbers["count"] for p in parts) / count
        return {"mean_ms": round(weighted, config.TIMING_DECIMALS), "count": count}
    return {
        "drift_pct": round(mean(p.numbers["drift_pct"] for p in parts), config.TIMING_DECIMALS),
        "target_bpm": parts[0].numbers["target_bpm"],
    }


def _runs_by_kind(problems: list[BarProblem]) -> list[list[BarProblem]]:
    """Group same-kind problems in consecutive bars (input is in bar order)."""
    runs: list[list[BarProblem]] = []
    open_run: dict[str, list[BarProblem]] = {}
    for problem in problems:
        run = open_run.get(problem.kind)
        if run is not None and run[-1].bar == problem.bar - 1:
            run.append(problem)
        else:
            run = open_run[problem.kind] = [problem]
            runs.append(run)
    return runs


def _merged_problem(run: list[BarProblem], alignment_quality: float) -> dict:
    confidences = [c for part in run for c in part.confidences]
    certainty = (mean(confidences) if confidences else NO_CONFIDENCE_CERTAINTY) * alignment_quality
    return {
        "kind": run[0].kind,
        "bars": [part.bar for part in run],
        "first_time_s": min(part.first_time_s for part in run),
        "measurement_ids": [mid for part in run for mid in part.measurement_ids],
        "size": mean(part.size for part in run),
        "certainty": certainty,
        "numbers": _merged_numbers(run[0].kind, run),
    }


def _form_problem(flag: dict) -> dict:
    numbers = {"label": flag["label"]}
    linked = flag.get("linked") or []
    if linked:
        numbers.update(link_kind=linked[0]["kind"], link_bar=linked[0]["bar"])
    return {
        "kind": config.PROBLEM_FORM,
        "bars": list(flag["bars"]),
        "first_time_s": flag["start_s"],
        "measurement_ids": [flag["id"]],
        "size": flag["severity"],
        "certainty": flag["confidence"],
        "numbers": numbers,
    }


def _scored(problem: dict) -> dict:
    bonus = 1 + config.MULTI_BAR_BONUS * (len(problem["bars"]) - 1)
    score = problem["size"] * problem["certainty"] * bonus
    return {
        **problem,
        "size": _round(problem["size"]),
        "certainty": _round(problem["certainty"]),
        "score": _round(score),
    }


def find_problems(diagnosis: dict, form_flags: list[dict]) -> list[dict]:
    """Merged, scored problems without ids or tiers. Form flags are never merged with each other."""
    problems = [_merged_problem(run, diagnosis["alignment_quality"]) for run in _runs_by_kind(bar_problems(diagnosis))]
    for flag in form_flags:
        if not flag.get("bars"):
            logger.warning("Form flag %s has no bars; left out of the ranking", flag.get("id"))
            continue
        problems.append(_form_problem(flag))
    return [_scored(problem) for problem in problems]
