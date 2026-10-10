"""init_plan: one ExerciseState per exercise of a saved plan, the session's before take and the whole-range exercise."""
import logging

from .. import store
from .progress import ADDED_BY_PLAN, ADDED_BY_PRACTICE, update_progress

logger = logging.getLogger("app.practice")

WHOLE_RANGE_TITLE = "Put it together"
WHOLE_RANGE_STEP_BPM = 4
WHOLE_RANGE_MAX_ERRORS = 1
WHOLE_RANGE_REPS_TO_PASS = 1
TAKE_PURPOSE = "take"


def new_exercise_state(plan_id: str, start_bpm: float, added_by: str) -> dict:
    return {"plan_id": plan_id, "current_bpm": start_bpm, "streak": 0, "fails_in_row": 0, "best_passed_bpm": None,
            "complete": False, "rep_ids": [], "added_by": added_by}


def first_before_take(takes: dict[str, dict]) -> dict | None:
    """The session's first take (purpose 'take') that was diagnosed and isn't can't-tell, or None."""
    for take in takes.values():
        diagnosis = take.get("diagnosis")
        if take.get("purpose", TAKE_PURPOSE) == TAKE_PURPOSE and diagnosis and not diagnosis.get("cant_tell"):
            return take
    return None


def _whole_range_exercise(plan_id: str, plan_exercises: list[dict], before: dict) -> dict:
    start = min(ex["start_bpm"] for ex in plan_exercises)
    bars = f"bar {before['bar_from']}" if before["bar_from"] == before["bar_to"] else f"bars {before['bar_from']} to {before['bar_to']}"
    return {
        "id": f"{plan_id}:whole", "title": WHOLE_RANGE_TITLE,
        "text": (f"Play {bars} all the way through at {start:g} BPM, then work up to {before['tempo_bpm']:g} BPM "
                 f"to hear how far you've come."),
        "bar_from": before["bar_from"], "bar_to": before["bar_to"], "start_bpm": start, "target_bpm": before["tempo_bpm"],
        "step_bpm": WHOLE_RANGE_STEP_BPM, "reps_to_pass": WHOLE_RANGE_REPS_TO_PASS,
        "pass_mark": {"max_errors": WHOLE_RANGE_MAX_ERRORS, "max_mean_timing_ms": None, "form_rule": None},
        "problem_ids": [], "claims": [],
    }


def _covers_before_bars(exercises: list[dict], before: dict) -> bool:
    return any(ex["bar_from"] == before["bar_from"] and ex["bar_to"] == before["bar_to"] for ex in exercises)


def init_plan(session_id: str, plan_id: str) -> None:
    """Create the practice state for a saved plan. Raises if the plan is unknown or the progress can't be saved.

    Exercises that already have a state are left untouched, so a newer plan only adds. While the session has no
    before take, the first diagnosed (not can't-tell) take becomes it, and if no exercise of this plan covers exactly its
    bars, 'Put it together' (id '{plan_id}:whole', added_by 'practice') is added after the plan's exercises.
    """
    session = store.get(session_id)
    exercises = session.plans[plan_id]["exercises"]
    before = first_before_take(session.takes)

    def add(progress: dict) -> None:
        for ex in exercises:
            progress["exercises"].setdefault(ex["id"], new_exercise_state(plan_id, ex["start_bpm"], ADDED_BY_PLAN))
        if progress["before_take"] is not None or before is None or not exercises:
            return
        progress["before_take"] = before["take_id"]
        if not _covers_before_bars(exercises, before):
            whole = _whole_range_exercise(plan_id, exercises, before)
            progress["added_exercises"][whole["id"]] = whole
            progress["exercises"][whole["id"]] = new_exercise_state(plan_id, whole["start_bpm"], ADDED_BY_PRACTICE)

    update_progress(session_id, add)
    logger.info("Practice state created for plan %s/%s (%d exercises)", session_id, plan_id, len(exercises))
