"""Score reader agent: a vision model reads a picture of one line of music, bar by bar.

Runs beside homr as a second opinion. Whatever goes wrong (AI switched off, bad settings, no
model access, Bedrock error, timeout, an answer that does not fit the Reading schema) the result
is None, 'no reading', and the cause is logged; the caller then reports 'not double-checked'.
"""
import logging
import threading
from pathlib import Path

from pydantic import ValidationError
from strands import Agent

from app.agents.config import ConfigError, Settings, get_settings
from app.agents.model import build_bedrock_model
from app.score.reading import Reading, ReadBar, ReadNote

__all__ = ["Reading", "ReadBar", "ReadNote", "read_score"]

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30
MAX_OUTPUT_TOKENS = 4096
IMAGE_FORMATS = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".gif": "gif", ".webp": "webp"}
PROMPT = (
    "This picture is a single line of printed music. Read it bar by bar, from the left, "
    "numbering the bars from 1. For every note give its pitch name with octave (for example E5 or "
    "Bb4; apply any sharps or flats from the key signature or earlier in the bar) or 'rest', and its "
    "length: whole, half, quarter, eighth or 16th, with 'dotted' in front if it is dotted. "
    "List every note and rest in every bar, in order. Read only what is printed; do not guess."
)


def _image_format(image_path: Path) -> str:
    try:
        return IMAGE_FORMATS[image_path.suffix.lower()]
    except KeyError:
        raise ValueError(f"unsupported image type '{image_path.suffix}' for {image_path.name}") from None


def _ask_model(settings: Settings, image_path: Path, cancel: threading.Event, timeout_s: float):
    """Run the Strands agent and return its raw structured output (not yet validated)."""
    model = build_bedrock_model(settings, settings.vision_model, timeout_seconds=max(1, int(timeout_s)))
    model.update_config(max_tokens=MAX_OUTPUT_TOKENS)
    agent = Agent(model=model, callback_handler=None)
    content = [
        {"text": PROMPT},
        {"image": {"format": _image_format(image_path), "source": {"bytes": image_path.read_bytes()}}},
    ]
    return agent(content, structured_output_model=Reading, cancel_signal=cancel).structured_output


def _run_with_timeout(settings: Settings, image_path: Path, timeout_s: float):
    """Call the model in a daemon thread so a hung call cannot hold the caller past timeout_s."""
    outcome: dict = {}
    cancel = threading.Event()

    def work() -> None:
        try:
            outcome["value"] = _ask_model(settings, image_path, cancel, timeout_s)
        except BaseException as exc:  # reported by the caller; a thread must not die silently
            outcome["error"] = exc

    worker = threading.Thread(target=work, name="score-reader", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        cancel.set()
        raise TimeoutError(f"the reader took longer than {timeout_s:g} seconds")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def read_score(image_path: Path, timeout_s: float = DEFAULT_TIMEOUT_S) -> Reading | None:
    """Read the score picture; None means 'no reading' (the cause is logged)."""
    try:
        settings = get_settings()
    except ConfigError:
        logger.exception("Score reader: AI settings are wrong, so there is no reading")
        return None
    if not settings.ai_enabled:
        logger.info("Score reader: AI_ENABLED is false, so there is no reading")
        return None
    try:
        return Reading.model_validate(_run_with_timeout(settings, Path(image_path), timeout_s))
    except ValidationError:
        logger.exception("Score reader: the model's answer did not fit the Reading schema")
    except TimeoutError:
        logger.exception("Score reader: timed out, so there is no reading")
    except Exception:
        logger.exception("Score reader: Bedrock call failed, so there is no reading")
    return None
