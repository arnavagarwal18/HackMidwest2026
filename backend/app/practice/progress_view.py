"""The Progress view for GET /sessions/{id}/progress: before and after snapshots and per-exercise counts, computed on read.

before is the Snapshot of progress.before_take, with its clean_bpm worked out from the takes up to and including it, so
later reps on the same bars (which overwrite session.clean_tempo) never move it. after is the Snapshot of the best scored rep, of any exercise whose bars
exactly match the before take's bars. Best means fewest errors, then the higher tempo, then the later rep.

events is the timeline, oldest first: one event per diagnosed take or scored rep, in the order the takes were recorded, plus an
"exercise_done" event right after the rep that completed an exercise. "time" is the rep's start (epoch seconds) when stored; takes
store no time, so their place in the list is their order.
"""
import logging

from .. import store
from ..diagnosis.timing import clean_tempo_for, clean_tempo_key
from .progress import find_exercise, read_progress
from .rules import ERROR_STATUSES, FORM_DONE
from .scoring import STATUS_SCORED

logger = logging.getLogger("app.practice.progress_view")

SOURCE_TAKE = "take"
SOURCE_REP = "rep"
EVENT_EXERCISE_DONE = "exercise_done"
TAKE_PURPOSE = "take"


def _count_errors(diagnosis: dict) -> int:
    wrong_or_missed = sum(1 for note in diagnosis.get("notes") or [] if note["status"] in ERROR_STATUSES)
    return wrong_or_missed + len(diagnosis.get("extras") or [])


def _clean_bpm_at_take(session: store.Session, take: dict) -> float | None:
    """The clean tempo of the take's bars as of that take: only it and the takes recorded before it count."""
    earlier = {}
    for take_id, other in session.takes.items():
        if take_id == take["take_id"]:
            break
        earlier[take_id] = other
    if take["diagnosis"].get("played_bpm") is None:
        return None
    return clean_tempo_for(earlier, take, take["diagnosis"])


def _snapshot(session: store.Session, take: dict, source: str) -> dict:
    diagnosis = take["diagnosis"]
    form = take.get("form") or {}
    return {
        "source": source, "take_id": take["take_id"], "bar_from": take["bar_from"], "bar_to": take["bar_to"],
        "errors": _count_errors(diagnosis), "error_rate": diagnosis.get("error_rate"),
        "played_bpm": diagnosis.get("played_bpm"),
        "clean_bpm": (_clean_bpm_at_take(session, take) if source == SOURCE_TAKE
                      else session.clean_tempo.get(clean_tempo_key(take["bar_from"], take["bar_to"]))),
        "form_flags": len(form.get("flags") or []),
        "form_checked": take["kind"] == "video" and take.get("form_status") == FORM_DONE,
    }


def _usable_diagnosis(take: dict | None) -> bool:
    return bool(take and take.get("diagnosis") and not take["diagnosis"].get("cant_tell"))


def _same_bars(exercise: dict | None, before: dict) -> bool:
    return bool(exercise) and (exercise["bar_from"], exercise["bar_to"]) == (before["bar_from"], before["bar_to"])


def _best_rep_snapshot(session: store.Session, progress: dict, before: dict) -> dict | None:
    """The best scored rep on the before take's bars, as a Snapshot labelled with its tempo; None if there is none."""
    candidates = []
    for position, (take_id, take) in enumerate(session.takes.items()):
        result = progress["reps"].get(take_id)
        if result is None or result["status"] != STATUS_SCORED or not _usable_diagnosis(take):
            continue
        if _same_bars(find_exercise(session.session_id, result["exercise_id"]), before):
            snapshot = _snapshot(session, take, SOURCE_REP)
            candidates.append(((snapshot["errors"], -result["tempo_bpm"], -position), result["tempo_bpm"], snapshot))
    if not candidates:
        return None
    _, tempo_bpm, snapshot = min(candidates, key=lambda candidate: candidate[0])
    return {**snapshot, "label": f"best practice rep at {tempo_bpm:g} BPM"}


def _exercise_summary(exercise: dict, state: dict, results: dict) -> dict:
    exercise_id = exercise["id"]
    scored = [results[rep_id] for rep_id in state["rep_ids"] if results.get(rep_id, {}).get("status") == STATUS_SCORED]
    return {
        "id": exercise_id, "title": exercise["title"], "start_bpm": exercise["start_bpm"],
        "target_bpm": exercise["target_bpm"], "best_passed_bpm": state["best_passed_bpm"], "complete": state["complete"],
        "reps": len(scored), "passes": sum(1 for rep in scored if rep["passed"]),
    }


def _exercise_title(session_id: str, exercise_id: str | None) -> str | None:
    exercise = find_exercise(session_id, exercise_id or "")
    return exercise["title"] if exercise else None


def _rep_event(session: store.Session, take: dict, result: dict) -> dict:
    return {
        **_snapshot(session, take, SOURCE_REP), "kind": SOURCE_REP, "time": take.get("started_at"),
        "exercise_id": result["exercise_id"], "exercise_title": _exercise_title(session.session_id, result["exercise_id"]),
        "tempo_bpm": result["tempo_bpm"], "passed": bool(result["passed"]), "reasons": result.get("reasons") or [],
    }


def _timeline_events(session: store.Session, progress: dict) -> list[dict]:
    """The timeline: diagnosed takes and scored reps in recorded order, each completed exercise right after its last rep."""
    events = []
    for take_id, take in session.takes.items():
        if not _usable_diagnosis(take):
            continue
        result = progress["reps"].get(take_id)
        if take.get("purpose", TAKE_PURPOSE) == TAKE_PURPOSE:
            events.append({**_snapshot(session, take, SOURCE_TAKE), "kind": SOURCE_TAKE, "time": None, "tempo_bpm": take.get("tempo_bpm")})
        elif result is not None and result["status"] == STATUS_SCORED:
            events.append(_rep_event(session, take, result))
            if result.get("exercise_complete"):
                events.append({"kind": EVENT_EXERCISE_DONE, "take_id": take_id, "time": take.get("started_at"),
                               "exercise_id": result["exercise_id"], "exercise_title": events[-1]["exercise_title"]})
    return events


def build_progress_view(session_id: str) -> dict:
    """{before, after, exercises, events}; an empty view for a session with no practice progress."""
    session = store.get(session_id)
    progress = read_progress(session_id)
    before_take = session.takes.get(progress["before_take"] or "")
    before = _snapshot(session, before_take, SOURCE_TAKE) if _usable_diagnosis(before_take) else None
    summaries = []
    for exercise_id, state in progress["exercises"].items():
        exercise = find_exercise(session_id, exercise_id)
        if exercise is None:
            logger.warning("Exercise %s of session %s has a state but no definition; left out of the progress view",
                           exercise_id, session_id)
            continue
        summaries.append(_exercise_summary(exercise, state, progress["reps"]))
    return {
        "before": before,
        "after": _best_rep_snapshot(session, progress, before_take) if before else None,
        "exercises": summaries,
        "events": _timeline_events(session, progress),
    }
