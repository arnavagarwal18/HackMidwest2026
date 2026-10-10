"""Practice progress stored in session.progress, and the exercise definitions it needs.

session.progress = {exercises: {ex_id: ExerciseState}, reps: {take_id: RepResult}, before_take, after_take,
added_exercises: {ex_id: exercise}}. Every write goes through `update_progress`, which serialises read-modify-write
cycles and saves with store.update.

`added_exercises` holds the definitions of exercises this module added itself ('Put it together', added_by 'practice'):
they are in no plan, so `find_exercise` (what GET exercise should use) looks in the plans first and then here.
"""
import copy
import threading
from typing import Callable

from .. import store

PROGRESS_KEY = "progress"
ADDED_BY_PLAN = "plan"
ADDED_BY_PRACTICE = "practice"

_progress_lock = threading.Lock()


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
    """Run mutate(progress) on a copy and save it, under one lock; returns the saved progress.

    Keys other modules keep in session.progress are preserved. If mutate raises, nothing is saved.
    """
    with _progress_lock:
        progress = read_progress(session_id)
        mutate(progress)
        store.update(session_id, PROGRESS_KEY, progress)
        return progress


def find_exercise(session_id: str, exercise_id: str) -> dict | None:
    """The exercise's definition: from a plan, else one practice added itself; None if the id is unknown."""
    session = store.get(session_id)
    for plan in session.plans.values():
        for exercise in plan["exercises"]:
            if exercise["id"] == exercise_id:
                return exercise
    return read_progress(session_id)["added_exercises"].get(exercise_id)


def needs_form_check(session_id: str, take_id: str) -> bool:
    """True when the rep take is a video and its exercise's pass mark has a form rule."""
    take = store.get(session_id).takes[take_id]
    exercise = find_exercise(session_id, take.get("exercise_id") or "")
    return take["kind"] == "video" and bool(exercise and exercise["pass_mark"].get("form_rule"))
