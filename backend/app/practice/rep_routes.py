"""Rep routes: upload a practice rep of an exercise (202, scored in the background) and fetch its RepResult."""
import logging
import time

from fastapi import APIRouter, File, Form, UploadFile

from .. import store
from ..errors import AppError
from ..takes.pipeline import start_pipeline
from ..takes.routes import accept_upload
from ..takes.validation import check_content_type, new_take_fields, original_file_name, parse_take_request
from .progress import exercise_with_state, read_progress, update_progress
from .scoring import STATUS_PROCESSING, processing_rep_result
from .stale_reps import sweep_stale_reps

logger = logging.getLogger("app.practice.routes")
router = APIRouter()

REP_PURPOSE = "rep"
NO_COUNT_IN = "0"


def check_can_start_rep(progress: dict, exercise_id: str) -> None:
    """Raise 409 wrong_state when the exercise is complete or one of its reps is still processing."""
    state = progress["exercises"][exercise_id]
    if state["complete"]:
        raise AppError(409, "wrong_state", "You've finished this exercise. Pick another one to practise.")
    if any(progress["reps"].get(rep_id, {}).get("status") == STATUS_PROCESSING for rep_id in state["rep_ids"]):
        raise AppError(409, "wrong_state", "Your last rep is still being checked. Wait for it, then play again.")


def _check_can_start_after_sweep(session_id: str, exercise_id: str) -> None:
    """The early 409 check on a copy of the progress with stale reps swept, so a stuck rep can't turn the upload away."""
    progress = read_progress(session_id)
    sweep_stale_reps(progress, store.get(session_id).takes, time.time(), store.session_dir(session_id))
    check_can_start_rep(progress, exercise_id)


def _claim_rep(session_id: str, exercise_id: str, take: dict) -> None:
    """In one progress update: sweep stale reps, re-check the 409 rules, write the processing RepResult and add the rep.

    The takes are read first because the update runs under the store's lock; the upload holds the takes lock, so
    they can't change before the update.
    """
    takes, now = store.get(session_id).takes, time.time()

    def start(progress: dict) -> None:
        swept = sweep_stale_reps(progress, takes, now, store.session_dir(session_id))
        if swept:
            logger.warning("Swept stale rep(s) of session %s stuck in processing: %s", session_id, ", ".join(swept))
        check_can_start_rep(progress, exercise_id)
        progress["reps"][take["take_id"]] = processing_rep_result(take)
        progress["exercises"][exercise_id]["rep_ids"].append(take["take_id"])

    update_progress(session_id, start)


def _release_rep(session_id: str, exercise_id: str, take_id: str) -> None:
    """Undo _claim_rep when the take could not be stored after it; failures here are logged, not raised."""
    def drop(progress: dict) -> None:
        progress["reps"].pop(take_id, None)
        rep_ids = progress["exercises"][exercise_id]["rep_ids"]
        progress["exercises"][exercise_id]["rep_ids"] = [rep_id for rep_id in rep_ids if rep_id != take_id]

    try:
        update_progress(session_id, drop)
    except Exception:
        logger.exception("Could not release rep %s/%s after its take failed to save", session_id, take_id)


@router.post("/sessions/{session_id}/exercises/{exercise_id}/reps", status_code=202)
def create_rep(
    session_id: str,
    exercise_id: str,
    file: UploadFile = File(...),
    kind: str | None = Form(None),
    source: str | None = Form(None),
    downbeat_s: str | None = Form(None),
) -> dict:
    exercise, state = exercise_with_state(session_id, exercise_id)
    _check_can_start_after_sweep(session_id, exercise_id)  # early answer; _claim_rep repeats it atomically
    content_type = check_content_type(file.content_type)
    request = parse_take_request(
        {"kind": kind, "source": source, "bar_from": str(exercise["bar_from"]), "bar_to": str(exercise["bar_to"]),
         "tempo_bpm": str(state["current_bpm"]), "count_in_beats": NO_COUNT_IN, "downbeat_s": downbeat_s},
        None,
    )

    def make_fields(take_id: str) -> dict:
        fields = new_take_fields(take_id, request, original_file_name(take_id, content_type))
        return {**fields, "purpose": REP_PURPOSE, "exercise_id": exercise_id, "started_at": time.time()}

    claimed: list[str] = []

    def claim(take: dict) -> None:
        _claim_rep(session_id, exercise_id, take)
        claimed.append(take["take_id"])

    try:
        take = accept_upload(session_id, file, make_fields, claim)
    except Exception:
        for take_id in claimed:
            _release_rep(session_id, exercise_id, take_id)
        raise
    start_pipeline(session_id, take["take_id"])
    return {"rep_id": take["take_id"], "tempo_bpm": take["tempo_bpm"], "status": STATUS_PROCESSING}


@router.get("/sessions/{session_id}/exercises/{exercise_id}/reps/{rep_id}")
def get_rep(session_id: str, exercise_id: str, rep_id: str) -> dict:
    exercise_with_state(session_id, exercise_id)
    rep = read_progress(session_id)["reps"].get(rep_id)
    if rep is None or rep["exercise_id"] != exercise_id:
        raise AppError(404, "rep_not_found", "We couldn't find that rep.")
    return rep
