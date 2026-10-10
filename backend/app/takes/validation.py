"""Checks for a new take's upload type and form fields, with messages a learner can act on."""
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from ..errors import AppError

logger = logging.getLogger("app.takes.validation")

# content type -> file extension; the first five are the accepted types listed in error messages
ACCEPTED_TYPES = {
    "audio/webm": ".webm",
    "audio/wav": ".wav",
    "audio/ogg": ".ogg",
    "video/webm": ".webm",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
}
_TYPE_ALIASES = {"audio/x-wav": "audio/wav", "audio/wave": "audio/wav"}
MAX_FILE_BYTES = 200 * 1024 * 1024
TEMPO_RANGE = (30.0, 240.0)
COUNT_IN_RANGE = (0, 8)
KINDS = ("mic", "video")
SOURCES = ("recorded", "uploaded")


@dataclass
class TakeRequest:
    kind: str
    source: str
    bar_from: int
    bar_to: int
    tempo_bpm: float
    count_in_beats: int
    downbeat_s: float | None


def bad_request(message: str) -> AppError:
    return AppError(422, "bad_request", message)


def normalise_content_type(content_type: str | None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    return _TYPE_ALIASES.get(base, base)


def check_content_type(content_type: str | None) -> str:
    """Return the canonical content type, or raise 415 listing the accepted types."""
    base = normalise_content_type(content_type)
    if base not in ACCEPTED_TYPES:
        raise AppError(415, "unsupported_type", f"That file type isn't supported. Use one of: {', '.join(ACCEPTED_TYPES)}.")
    return base


def _number(raw: str | None, name: str, cast):
    if raw is None or raw.strip() == "":
        raise bad_request(f"Missing {name}.")
    try:
        return cast(raw)
    except ValueError:
        raise bad_request(f"{name} must be a number.")


def _choice(raw: str | None, name: str, choices: tuple[str, ...]) -> str:
    if raw not in choices:
        raise bad_request(f"{name} must be one of: {', '.join(choices)}.")
    return raw


def score_bar_count(score_path: Path) -> int | None:
    """Number of bars in score.json (key 'bars'), or None when the score isn't there or can't be read."""
    if not score_path.is_file():
        return None
    try:
        bars = json.loads(score_path.read_text(encoding="utf-8")).get("bars")
    except (OSError, ValueError, AttributeError):
        logger.warning("Could not read bar count from %s; skipping the bar range check", score_path, exc_info=True)
        return None
    return len(bars) if isinstance(bars, list) else None


def parse_take_request(form: dict[str, str | None], bar_count: int | None) -> TakeRequest:
    kind = _choice(form.get("kind"), "kind", KINDS)
    source = _choice(form.get("source"), "source", SOURCES)
    bar_from = _number(form.get("bar_from"), "bar_from", int)
    bar_to = _number(form.get("bar_to"), "bar_to", int)
    tempo = _number(form.get("tempo_bpm"), "tempo_bpm", float)
    count_in = _number(form.get("count_in_beats"), "count_in_beats", int)
    downbeat = form.get("downbeat_s")
    downbeat_s = _number(downbeat, "downbeat_s", float) if source == "recorded" else None

    if bar_from < 1 or bar_from > bar_to:
        raise bad_request("Pick a starting bar that is 1 or more and not after the ending bar.")
    if bar_count is not None and bar_to > bar_count:
        raise bad_request(f"The score has {bar_count} bars. Pick bars within it.")
    if downbeat_s is not None and not (math.isfinite(downbeat_s) and downbeat_s >= 0):
        raise bad_request("downbeat_s must be a time in seconds, 0 or more.")
    if not TEMPO_RANGE[0] <= tempo <= TEMPO_RANGE[1]:
        raise bad_request(f"Tempo must be between {TEMPO_RANGE[0]:.0f} and {TEMPO_RANGE[1]:.0f} beats per minute.")
    if not COUNT_IN_RANGE[0] <= count_in <= COUNT_IN_RANGE[1]:
        raise bad_request(f"Count-in must be between {COUNT_IN_RANGE[0]} and {COUNT_IN_RANGE[1]} beats.")
    return TakeRequest(kind, source, bar_from, bar_to, tempo, count_in, downbeat_s)


def original_file_name(take_id: str, content_type: str) -> str:
    """{take_id}{ext}; a wav original gets '_upload' so it can't collide with the extracted {take_id}.wav."""
    ext = ACCEPTED_TYPES[content_type]
    return f"{take_id}_upload{ext}" if ext == ".wav" else f"{take_id}{ext}"


def new_take_fields(take_id: str, request: TakeRequest, file_name: str) -> dict:
    """The stored Take record for a freshly uploaded file."""
    return {
        "purpose": "take", "kind": request.kind, "source": request.source,
        "file": file_name, "audio": f"{take_id}.wav", "duration_s": 0.0,
        "bar_from": request.bar_from, "bar_to": request.bar_to, "tempo_bpm": request.tempo_bpm,
        "count_in_beats": request.count_in_beats, "downbeat_s": request.downbeat_s,
        "calib_end_s": 0, "status": "processing", "error": None,
        "form_status": "none", "notes": [], "calibrated": False,
    }
