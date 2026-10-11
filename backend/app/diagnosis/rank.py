"""Steps 7-8: rank a take's problems, assign tiers and ids, and write the tier-1 sentences."""
from . import config
from .problems import find_problems
from .sentences import build_sentence


def _is_tier1_candidate(problem: dict) -> bool:
    return problem["certainty"] >= config.TIER1_MIN_CERTAINTY and problem["score"] >= config.TIER1_MIN_SCORE


def _tiers(sorted_problems: list[dict]) -> list[int]:
    """Tier 1: the first TIER1_MAX sure-enough problems; tier 2: the next TIER2_MAX of the rest; the rest tier 3."""
    tier1 = [i for i, problem in enumerate(sorted_problems) if _is_tier1_candidate(problem)][: config.TIER1_MAX]
    tiers = [1 if i in tier1 else 0 for i in range(len(sorted_problems))]
    others = [i for i, tier in enumerate(tiers) if tier == 0]
    for position, index in enumerate(others):
        tiers[index] = 2 if position < config.TIER2_MAX else 3
    return tiers


def _bars_text(first: int, last: int) -> str:
    return f"bar {first}" if first == last else f"bars {first}-{last}"


def range_note(diagnosis: dict, next_id: str) -> dict | None:
    """The tier-3 'range' problem when at least one whole bar was not played: 'You played bars a-b of c-d.'"""
    played = diagnosis.get("played_bars")
    if not diagnosis.get("not_played_count") or not played:
        return None
    asked = [diagnosis["bars"][0]["bar"], diagnosis["bars"][-1]["bar"]]
    played_notes = [n for n in diagnosis["notes"] if n["status"] != config.STATUS_NOT_PLAYED]
    return {
        "id": next_id,
        "kind": config.PROBLEM_RANGE,
        "bars": [],
        "first_time_s": min(n["expected_onset_s"] for n in played_notes),
        "measurement_ids": [],
        "size": 0.0,
        "certainty": 1.0,
        "score": 0.0,
        "numbers": {"played_from": played[0], "played_to": played[1], "bar_from": asked[0], "bar_to": asked[1]},
        "text": f"You played {_bars_text(*played)} of {asked[0]}-{asked[1]}.",
        "tier": config.RANGE_TIER,
    }


def rank(take_id: str, diagnosis: dict, form_flags: list[dict]) -> dict:
    """{problems, tier1} for a diagnosis (notes, extras, bars, ...) and the take's form flags.

    A can't-tell diagnosis ranks nothing. Problem ids follow the ranking, so they change when it does.
    A take that skipped whole bars ends with the tier-3 range note (no sentence).
    """
    if diagnosis["cant_tell"]:
        return {"problems": [], "tier1": []}
    found = sorted(find_problems(diagnosis, form_flags), key=lambda p: (-p["score"], p["first_time_s"]))
    tiers = _tiers(found)
    problems = [
        {"id": f"p:{take_id}:{k}", **problem, "tier": tier} for k, (problem, tier) in enumerate(zip(found, tiers))
    ]
    note = range_note(diagnosis, f"p:{take_id}:{len(problems)}")
    return {
        "problems": problems + ([note] if note else []),
        "tier1": [build_sentence(p) for p in problems if p["tier"] == 1],
    }
