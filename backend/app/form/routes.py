"""GET /sessions/{id}/takes/{take}/tracks: the saved per-frame landmarks of a video take."""
import gzip
import logging

from fastapi import APIRouter, Request, Response

from ..errors import AppError, storage_error
from ..takes.take_store import get_take
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
