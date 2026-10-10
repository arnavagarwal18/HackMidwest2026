"""Form routes: GET /sessions/{id}/takes/{take}/tracks (saved landmarks of a video take) and POST /sessions/{id}/camera-check."""
import gzip
import logging

import cv2
import numpy as np
from fastapi import APIRouter, File, Request, Response, UploadFile

from .. import store
from ..errors import AppError, storage_error
from ..takes.take_store import get_take
from . import config
from .camera_check import check_camera_frame
from .errors import FormUnavailable
from .track import tracks_path

logger = logging.getLogger("app.form.routes")
router = APIRouter()


def _accepts_gzip(request: Request) -> bool:
    return "gzip" in request.headers.get("accept-encoding", "").lower()


@router.get("/sessions/{session_id}/takes/{take_id}/tracks")
def get_tracks(session_id: str, take_id: str, request: Request) -> Response:
    take = get_take(session_id, take_id)
    if take["kind"] != "video":
        raise AppError(404, "no_tracks", "This take has no video to show.")
    if take.get("form_status") != "done":
        raise AppError(409, "wrong_state", "Form analysis not finished.")
    path = tracks_path(session_id, take_id)
    try:
        body = path.read_bytes()
    except FileNotFoundError:
        logger.warning("Take %s/%s is done but %s is missing", session_id, take_id, path)
        raise AppError(404, "no_tracks", "This take has no video to show.")
    except OSError:
        logger.exception("Could not read tracks file %s", path)
        raise storage_error()
    headers = {"Vary": "Accept-Encoding"}
    if _accepts_gzip(request):
        body, headers["Content-Encoding"] = gzip.compress(body), "gzip"
    return Response(body, media_type="application/json", headers=headers)


def _decode_frame(upload: UploadFile) -> np.ndarray:
    data = upload.file.read(config.CAMERA_CHECK_MAX_BYTES + 1)
    if len(data) > config.CAMERA_CHECK_MAX_BYTES:
        raise AppError(413, "file_too_large", f"That picture is too big. Keep it under {config.CAMERA_CHECK_MAX_BYTES // (1024 * 1024)} MB.")
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
    if frame is None:
        raise AppError(415, "unsupported_type", "That file isn't a picture we can read. Send a JPEG frame from the camera.")
    return frame


@router.post("/sessions/{session_id}/camera-check")
def camera_check(session_id: str, file: UploadFile = File(...)) -> dict:
    session = store.get(session_id)
    frame = _decode_frame(file)
    try:
        return check_camera_frame(frame, session.instrument)
    except FormUnavailable as exc:
        logger.error("Camera check unavailable for session %s: %s", session_id, exc)
        raise AppError(503, exc.code, exc.message)
