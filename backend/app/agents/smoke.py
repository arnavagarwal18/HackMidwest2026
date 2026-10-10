"""Checks that the AI models answer: run `python -m app.agents.smoke` from backend/."""
import logging
import struct
import sys
import time
import zlib
from pathlib import Path

from strands import Agent

from app.agents.config import ConfigError, Settings, get_settings
from app.agents.model import build_bedrock_model
from app.agents.smoke_errors import describe_config_error, describe_failure

logger = logging.getLogger("app.agents.smoke")
LOG_FILE = Path(__file__).resolve().parents[2] / "smoke.log"

TEXT_PROMPT = "Reply with the single word: ready"
IMAGE_PROMPT = "What colour is this image? Answer with one word."


def tiny_red_png(size: int = 16) -> bytes:
    """A solid red size x size PNG, built without an imaging library."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    row = b"\x00" + b"\xff\x00\x00" * size
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b"")


def _ask(settings: Settings, model_id: str, content: list[dict]) -> str:
    agent = Agent(model=build_bedrock_model(settings, model_id), callback_handler=None)
    return str(agent(content)).strip()


def _run_step(settings: Settings, step: str, model_id: str, content: list[dict]) -> bool:
    started = time.monotonic()
    try:
        reply = _ask(settings, model_id, content)
    except Exception as exc:
        logger.error("Smoke test %s step failed", step, exc_info=exc)
        print(f"FAILED: {describe_failure(exc, step, model_id, settings)} (details: {LOG_FILE.name})")
        return False
    print(f"{step} ({model_id}): {reply!r} in {time.monotonic() - started:.1f}s")
    return True


def main() -> int:
    logging.basicConfig(level=logging.ERROR, filename=LOG_FILE, filemode="w")
    try:
        settings = get_settings()
        if not settings.ai_enabled:
            raise ConfigError("AI is switched off (AI_ENABLED is not true). Set AI_ENABLED=true.")
    except ConfigError as exc:
        print(f"FAILED: {describe_config_error(exc)}")
        return 1
    steps = (
        ("text model", settings.text_model, [{"text": TEXT_PROMPT}]),
        (
            "vision model",
            settings.vision_model,
            [{"text": IMAGE_PROMPT}, {"image": {"format": "png", "source": {"bytes": tiny_red_png()}}}],
        ),
    )
    return 0 if all(_run_step(settings, *step) for step in steps) else 1


if __name__ == "__main__":
    sys.exit(main())
