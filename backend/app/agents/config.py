"""AI settings read from backend/.env (and the process environment, which wins)."""
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"", "false", "0", "no", "off"}


class ConfigError(Exception):
    """A setting is missing or wrong; the message says which one and how to fix it."""


@dataclass(frozen=True)
class Settings:
    region: str
    text_model: str
    vision_model: str
    aws_profile: str
    ai_enabled: bool


def _parse_bool(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ConfigError(f"{name} must be true or false, not '{raw}'. Fix it in backend/.env.")


def parse_settings(env: Mapping[str, str | None]) -> Settings:
    def get(name: str) -> str:
        return (env.get(name) or "").strip()

    settings = Settings(
        region=get("BEDROCK_REGION"),
        text_model=get("BEDROCK_TEXT_MODEL"),
        vision_model=get("BEDROCK_VISION_MODEL"),
        aws_profile=get("AWS_PROFILE"),
        ai_enabled=_parse_bool("AI_ENABLED", get("AI_ENABLED")),
    )
    if settings.ai_enabled:
        for name, value in (
            ("BEDROCK_REGION", settings.region),
            ("BEDROCK_TEXT_MODEL", settings.text_model),
            ("BEDROCK_VISION_MODEL", settings.vision_model),
        ):
            if not value:
                raise ConfigError(f"AI_ENABLED is true but {name} is empty. Set it in backend/.env (see backend/.env.example).")
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings from backend/.env, overridden by real environment variables."""
    return parse_settings({**dotenv_values(ENV_FILE), **os.environ})
