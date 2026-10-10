"""Photo scan routes: start a scan of an uploaded photo, and poll its status."""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app import store
from app.errors import AppError, storage_error
from app.score import scan_job
from app.score.model import Score
from app.score.routes import raise_if_locked

logger = logging.getLogger("app.score.photo_routes")
router = APIRouter()

MAX_PHOTO_BYTES = 15 * 1024 * 1024
PHOTO_SIGNATURES = {b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png"}
PHOTO_FILENAME_STEM = "photo_upload"
_start_lock = threading.Lock()  # makes "check not scanning, then mark scanning" one step


def _photo_suffix(data: bytes) -> str | None:
    return next((suffix for magic, suffix in PHOTO_SIGNATURES.items() if data.startswith(magic)), None)


def _read_photo(upload: UploadFile) -> tuple[bytes, str]:
    data = upload.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise AppError(413, "file_too_large", f"That photo is too big. Photos can be at most {MAX_PHOTO_BYTES // (1024 * 1024)} MB.")
    suffix = _photo_suffix(data)
    if suffix is None:
        raise AppError(415, "unsupported_type", "That file isn't a JPEG or PNG photo.")
    return data, suffix


def _save_photo(session_id: str, data: bytes, suffix: str) -> Path:
    folder = store.session_dir(session_id)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob(f"{PHOTO_FILENAME_STEM}.*"):
            old.unlink()
        path = folder / f"{PHOTO_FILENAME_STEM}{suffix}"
        path.write_bytes(data)
    except OSError:
        logger.exception("Could not save the photo in %s", folder)
        raise storage_error()
    return path


def _mark_scanning(session_id: str) -> None:
    store.update(session_id, "score_error", None)
    store.update(session_id, "doubtful_bars", [])
    store.update(session_id, "double_checked", False)
    store.update(session_id, "score_status", "scanning")


def _claim_scan(session_id: str, data: bytes, suffix: str) -> Path:
    with _start_lock:
        raise_if_locked(store.get(session_id).score_status)
        photo = _save_photo(session_id, data, suffix)
        _mark_scanning(session_id)
    return photo


@router.post("/sessions/{session_id}/score/photo", status_code=202)
async def post_score_photo(session_id: str, request: Request) -> dict:
    raise_if_locked(store.get(session_id).score_status)
    upload = (await request.form()).get("file")
    if not isinstance(upload, UploadFile):
        raise AppError(422, "bad_request", "Choose a photo to upload in the 'file' field.")
    data, suffix = await run_in_threadpool(_read_photo, upload)
    photo = await run_in_threadpool(_claim_scan, session_id, data, suffix)
    scan_job.start_scan(session_id, photo)
    return {"score_status": "scanning"}


@router.get("/sessions/{session_id}/score/status")
def get_score_status(session_id: str) -> dict:
    session = store.get(session_id)
    bars, warnings = None, []
    if session.score_status in ("scanned", "confirmed"):
        try:
            score = Score.load(store.session_dir(session_id))
        except (OSError, ValueError):
            logger.exception("Could not load the saved score for session %s", session_id)
            raise storage_error()
        bars, warnings = len(score.bars), score.warnings
    return {
        "score_status": session.score_status,
        "score_error": session.score_error,
        "score_error_message": scan_job.SCAN_MESSAGES.get(session.score_error),
        "bars": bars,
        "doubtful_bars": session.doubtful_bars,
        "double_checked": session.double_checked,
        "warnings": warnings,
    }
