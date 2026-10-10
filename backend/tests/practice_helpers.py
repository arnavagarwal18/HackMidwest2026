"""Builders for the practice tests: a session with a plan, diagnosed takes and rep takes, written straight to the store."""
from app import store

PASS_MARK = {"max_errors": 0, "max_mean_timing_ms": None, "form_rule": None}


def exercise(ex_id="ex1", bar_from=2, bar_to=3, start_bpm=60, target_bpm=72, step_bpm=4, reps_to_pass=2, **pass_mark):
    return {"id": ex_id, "title": "Work", "text": "Play it.", "bar_from": bar_from, "bar_to": bar_to, "start_bpm": start_bpm,
            "target_bpm": target_bpm, "step_bpm": step_bpm, "reps_to_pass": reps_to_pass,
            "pass_mark": {**PASS_MARK, **pass_mark}, "problem_ids": [], "claims": []}


def note(bar, status="ok", timing_ms=0.0):
    return {"id": f"n{bar}{status}", "bar": bar, "status": status, "timing_ms": timing_ms}


def diagnosis(*notes, cant_tell=False):
    return {"notes": list(notes), "extras": [], "cant_tell": cant_tell}


def clean_diagnosis():
    return diagnosis(note(2), note(3))


def bad_diagnosis():
    return diagnosis(note(2), note(3, "wrong", None))


def save_plan(session_id, plan_id, *exercises):
    session = store.get(session_id)
    store.update(session_id, "plans", {**session.plans, plan_id: {"id": plan_id, "exercises": list(exercises)}})


def add_take(session_id, take_id, **fields):
    take = {"take_id": take_id, "purpose": "take", "kind": "mic", "status": "done", "error": None, "form_status": "none",
            "form": None, "source": "recorded", "audio": "x.wav", "notes": [], "bar_from": 1, "bar_to": 4, "tempo_bpm": 90.0, "diagnosis": clean_diagnosis(), **fields}
    session = store.get(session_id)
    store.update(session_id, "takes", {**session.takes, take_id: take})
    return take


def add_rep(session_id, take_id, exercise_id="ex1", tempo_bpm=60.0, diag=None, **fields):
    return add_take(session_id, take_id, purpose="rep", exercise_id=exercise_id, tempo_bpm=tempo_bpm,
                    diagnosis=diag or clean_diagnosis(), **fields)
