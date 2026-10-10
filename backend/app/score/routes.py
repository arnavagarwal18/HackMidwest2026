"""Score routes: upload or pick a built-in piece, list built-ins, confirm, and read the score back."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from app import store
from app.errors import AppError, storage_error
from app.score import builtins, ingest
from app.score.exceptions import BadScoreFile, BuiltinNotFound
from app.score.model import Score

logger = logging.getLogger("app.score.routes")
router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MUSICXML_MEDIA_TYPE = "application/vnd.recordare.musicxml+xml"
BAD_SCORE_MESSAGE = "This file couldn't be read as sheet music."
LOCKED_MESSAGES = {
    "confirmed": "This session's score is already confirmed. Start a new session to use a different score.",
    "scanning": "This session's score is still being scanned. Wait for it to finish.",
}


def _wrong_state(message: str) -> AppError:
    return AppError(409, "wrong_state", message)


def raise_if_locked(status: str) -> None:
    """409 wrong_state while the score is confirmed or being scanned (shared with the photo route)."""
    if status in LOCKED_MESSAGES:
        raise _wrong_state(LOCKED_MESSAGES[status])


def _bad_request(message: str) -> AppError:
    return AppError(422, "bad_request", message)


def _load_score(session_id: str) -> Score:
    folder = store.session_dir(session_id)
    try:
        return Score.load(folder)
    except (OSError, ValueError):
        logger.exception("Could not load the saved score in %s", folder)
        raise storage_error()


def _read_upload_bytes(upload: UploadFile) -> bytes:
    if Path(upload.filename or "").suffix.lower() not in ingest.UPLOAD_SUFFIXES:
        raise AppError(415, "unsupported_type", f"That file type isn't supported. Use one of: {', '.join(ingest.UPLOAD_SUFFIXES)}.")
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(413, "file_too_large", f"That file is too big. Files can be at most {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    return data


async def _read_request(request: Request) -> tuple[str, tuple[str, bytes] | str]:
    """Returns ("file", (filename, bytes)) for a multipart upload or ("builtin", piece_id) for a JSON body."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        upload = (await request.form()).get("file")
        if not isinstance(upload, UploadFile):
            raise _bad_request("Choose a file to upload in the 'file' field.")
        return "file", (upload.filename, await run_in_threadpool(_read_upload_bytes, upload))
    try:
        body = await request.json()
    except ValueError:
        raise _bad_request("Send a file, or JSON like {\"builtin\": \"piece_id\"}.")
    piece_id = body.get("builtin") if isinstance(body, dict) else None
    if not isinstance(piece_id, str) or not piece_id:
        raise _bad_request("Send a file, or JSON like {\"builtin\": \"piece_id\"}.")
    return "builtin", piece_id


def _save_score(session_id: str, kind: str, payload) -> Score:
    folder = store.session_dir(session_id)
    try:
        if kind == "builtin":
            return ingest.ingest_builtin(folder, payload)
        filename, data = payload
        return ingest.ingest_upload(folder, filename, data)
    except BadScoreFile as exc:
        logger.info("Rejected score for session %s: %s", session_id, exc)
        raise AppError(422, "bad_score_file", BAD_SCORE_MESSAGE)
    except BuiltinNotFound:
        raise AppError(404, "builtin_not_found", "We don't have that built-in piece.")
    except OSError:
        logger.exception("Could not write the score files in %s", folder)
        raise storage_error()


@router.post("/sessions/{session_id}/score/file")
async def post_score_file(session_id: str, request: Request) -> dict:
    session = store.get(session_id)
    raise_if_locked(session.score_status)
    kind, payload = await _read_request(request)
    score = await run_in_threadpool(_save_score, session_id, kind, payload)
    store.update(session_id, "score_error", None)
    store.update(session_id, "doubtful_bars", [])
    store.update(session_id, "double_checked", False)
    store.update(session_id, "referee", None)
    store.update(session_id, "score_status", "scanned")
    return {
        "score_status": "scanned",
        "bars": len(score.bars),
        "doubtful_bars": [],
        "double_checked": False,
        "warnings": score.warnings,
    }


@router.get("/builtins")
def get_builtins(instrument: str | None = None) -> list[dict]:
    try:
        return builtins.list_builtins(instrument)
    except (OSError, ValueError):
        raise storage_error()


@router.post("/sessions/{session_id}/score/confirm")
def confirm_score(session_id: str) -> dict:
    status = store.get(session_id).score_status
    if status != "scanned":
        raise _wrong_state("There's no scanned score to confirm yet. Add your sheet music first.")
    score = _load_score(session_id)
    store.update(session_id, "score_status", "confirmed")
    return {
        "score_status": "confirmed",
        "bars": len(score.bars),
        "tempo_bpm": score.tempo_bpm,
        "time_signature": list(score.time_signature),
    }


@router.get("/sessions/{session_id}/score")
def get_score_text(session_id: str, format: Literal["musicxml", "json"] = Query("musicxml")) -> Response:
    if store.get(session_id).score_status not in ("scanned", "confirmed"):
        raise _wrong_state("This session doesn't have a score yet. Add your sheet music first.")
    if format == "json":
        return Response(content=_load_score(session_id).to_json(), media_type="application/json")
    folder = store.session_dir(session_id)
    try:
        text = ingest.read_musicxml(folder)
    except OSError:
        raise storage_error()
    return Response(content=text, media_type=MUSICXML_MEDIA_TYPE)
