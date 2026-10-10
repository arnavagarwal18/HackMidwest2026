"""Built-in practice pieces: backend/app/score/builtins/{piece_id}.musicxml listed in builtins.json."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.score.exceptions import BuiltinNotFound

logger = logging.getLogger(__name__)

BUILTINS_DIR = Path(__file__).resolve().parent / "builtins"
LISTING_FILE = "builtins.json"


def list_builtins(instrument: str | None = None) -> list[dict]:
    """Built-in pieces as { piece_id, title, instrument, bars }, filtered by instrument if given."""
    path = BUILTINS_DIR / LISTING_FILE
    try:
        pieces = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Could not read the built-in piece list at %s", path)
        raise
    return [piece for piece in pieces if instrument is None or piece["instrument"] == instrument]


def builtin_path(piece_id: str) -> Path:
    """Path of a built-in piece's MusicXML; raises BuiltinNotFound for an unknown piece_id."""
    if piece_id not in {piece["piece_id"] for piece in list_builtins()}:
        raise BuiltinNotFound(f"No built-in piece called '{piece_id}'.")
    return BUILTINS_DIR / f"{piece_id}.musicxml"
