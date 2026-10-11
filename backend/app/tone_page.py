"""GET /tone?instrument=...&note=...: the phone tone page. The page itself reads the query from its own address."""
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from .errors import AppError

logger = logging.getLogger("app.tone_page")
router = APIRouter()

TONE_PAGE = Path(__file__).resolve().parents[2] / "frontend" / "tone.html"


@router.get("/tone")
def tone_page() -> FileResponse:
    if not TONE_PAGE.is_file():
        logger.error("The tone page %s is missing", TONE_PAGE)
        raise AppError(500, "server_error", "The tone page is missing. Tell the team.")
    return FileResponse(TONE_PAGE, media_type="text/html")
