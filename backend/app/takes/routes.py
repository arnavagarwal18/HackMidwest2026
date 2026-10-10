"""Take routes: upload a take (202, processed in the background) and fetch its original media."""
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from .. import store
from ..errors import AppError, storage_error
from .pipeline import start_pipeline
from .take_store import add_take
from .validation import (
    MAX_FILE_BYTES,
    check_content_type,
    new_take_fields,
    original_file_name,
    parse_take_request,
    score_bar_count,
)

logger = logging.getLogger("app.takes.routes")
router = APIRouter()

_COPY_CHUNK = 1024 * 1024


def _save_upload(upload: UploadFile, target: Path) -> None:
    """Copy the upload into the session folder, refusing anything over the size limit."""
    written = 0
    try:
        with open(target, "wb") as out:
            while chunk := upload.file.read(_COPY_CHUNK):
                written += len(chunk)
                if written > MAX_FILE_BYTES:
                    break
                out.write(chunk)
    except OSError:
        logger.exception("Could not save the uploaded take to %s", target)
        target.unlink(missing_ok=True)
        raise storage_error()
    if written > MAX_FILE_BYTES:
        target.unlink(missing_ok=True)
        raise AppError(413, "file_too_large", f"That file is too big. Keep it under {MAX_FILE_BYTES // (1024 * 1024)} MB.")


@router.post("/sessions/{session_id}/takes", status_code=202)
def create_take(
    session_id: str,
    file: UploadFile = File(...),
    kind: str | None = Form(None),
    source: str | None = Form(None),
    bar_from: str | None = Form(None),
    bar_to: str | None = Form(None),
    tempo_bpm: str | None = Form(None),
    count_in_beats: str | None = Form(None),
    downbeat_s: str | None = Form(None),
) -> dict:
    session = store.get(session_id)
    if session.score_status != "confirmed":
        raise AppError(409, "wrong_state", "Confirm your sheet music before recording a take.")
    content_type = check_content_type(file.content_type)
    folder = store.session_dir(session_id)
    request = parse_take_request(
        {"kind": kind, "source": source, "bar_from": bar_from, "bar_to": bar_to,
         "tempo_bpm": tempo_bpm, "count_in_beats": count_in_beats, "downbeat_s": downbeat_s},
        score_bar_count(folder / "score.json"),
    )

    temp_path = folder / f"upload-{uuid.uuid4().hex}.tmp"
    _save_upload(file, temp_path)
    try:
        take = add_take(
            session_id,
            lambda take_id: new_take_fields(take_id, request, original_file_name(take_id, content_type)),
            lambda take: _move_into_place(temp_path, folder / take["file"]),
        )
    finally:
        temp_path.unlink(missing_ok=True)
    start_pipeline(session_id, take["take_id"])
    return {"take_id": take["take_id"], "status": "processing"}


def _move_into_place(temp_path: Path, target: Path) -> None:
    try:
        os.replace(temp_path, target)
    except OSError:
        logger.exception("Could not move the uploaded take to %s", target)
        raise storage_error()


@router.get("/sessions/{session_id}/takes/{take_id}/media")
def get_take_media(session_id: str, take_id: str) -> FileResponse:
    take = store.get(session_id).takes.get(take_id)
    path = store.session_dir(session_id) / take["file"] if take else None
    if path is None or not path.is_file():
        logger.warning("Media for take %s/%s is missing (%s)", session_id, take_id, path)
        raise AppError(404, "take_not_found", "We couldn't find that take.")
    media_type = "audio/webm" if take["kind"] == "mic" and path.suffix == ".webm" else None
    return FileResponse(path, media_type=media_type)
