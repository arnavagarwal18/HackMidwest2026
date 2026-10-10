"""Practice progress stored in session.progress, and the exercise definitions it needs.

session.progress = {exercises: {ex_id: ExerciseState}, reps: {take_id: RepResult}, before_take, after_take,
added_exercises: {ex_id: exercise}}. Every write goes through `update_progress`, which does its read-modify-write inside
store.modify, under the store's per-session lock.

`added_exercises` holds the definitions of exercises this module added itself ('Put it together', added_by 'practice'):
they are in no plan, so `find_exercise` (what GET exercise should use) looks in the plans first and then here.
"""
import copy
from typing import Callable

from .. import store
from ..errors import AppError

PROGRESS_KEY = "progress"
ADDED_BY_PLAN = "plan"
ADDED_BY_PRACTICE = "practice"


def _with_defaults(progress: dict) -> dict:
    filled = copy.deepcopy(progress)
    for key in ("exercises", "reps", "added_exercises"):
        filled.setdefault(key, {})
    for key in ("before_take", "after_take"):
        filled.setdefault(key, None)
    return filled


def read_progress(session_id: str) -> dict:
    """A copy of the session's practice progress, with every key present."""
    return _with_defaults(store.get(session_id).progress)


def update_progress(session_id: str, mutate: Callable[[dict], None]) -> dict:
    """Run mutate(progress) on a copy and save it with store.modify, so the read-modify-write holds the session lock.

    Keys other modules keep in session.progress are preserved. If mutate raises, nothing is saved.
    `mutate` runs under that lock, so it must not call the store.
    """
    def change(current: dict) -> dict:
        progress = _with_defaults(current)
        mutate(progress)
        return progress

    return store.modify(session_id, PROGRESS_KEY, change).progress


def find_exercise(session_id: str, exercise_id: str) -> dict | None:
    """The exercise's definition: from a plan, else one practice added itself; None if the id is unknown."""
    session = store.get(session_id)
    for plan in session.plans.values():
        for exercise in plan["exercises"]:
            if exercise["id"] == exercise_id:
                return exercise
    return read_progress(session_id)["added_exercises"].get(exercise_id)


def exercise_with_state(session_id: str, exercise_id: str) -> tuple[dict, dict]:
    """The exercise's definition and its ExerciseState; raises 404 session_not_found or exercise_not_found."""
    exercise = find_exercise(session_id, exercise_id)
    state = read_progress(session_id)["exercises"].get(exercise_id)
    if exercise is None or state is None:
        raise AppError(404, "exercise_not_found", "We couldn't find that exercise.")
    return exercise, state


def needs_form_check(session_id: str, take_id: str) -> bool:
    """True when the rep take is a video and its exercise's pass mark has a form rule."""
    take = store.get(session_id).takes[take_id]
    exercise = find_exercise(session_id, take.get("exercise_id") or "")
    return take["kind"] == "video" and bool(exercise and exercise["pass_mark"].get("form_rule"))
