"""Builds Bedrock models for Strands agents from Settings."""
import copy
from typing import Any

import boto3
from botocore.config import Config as BotocoreConfig
from strands.models import BedrockModel

from app.agents.config import Settings

DEFAULT_TIMEOUT_SECONDS = 10
AGENT_READ_TIMEOUT_SECONDS = 20
AGENT_RETRIES = 2
AGENT_TEMPERATURE = 0.2
AGENT_MAX_TOKENS = 2000


def _bedrock(settings: Settings, model_id: str, connect_timeout: int, read_timeout: int, attempts: int, **model_args) -> BedrockModel:
    """A BedrockModel using the AWS CLI profile named in settings (or the default AWS credential chain)."""
    session = boto3.Session(profile_name=settings.aws_profile or None, region_name=settings.region)
    client_config = BotocoreConfig(connect_timeout=connect_timeout, read_timeout=read_timeout, retries={"max_attempts": attempts})
    return BedrockModel(model_id=model_id, boto_session=session, boto_client_config=client_config, **model_args)


def build_bedrock_model(settings: Settings, model_id: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> BedrockModel:
    return _bedrock(settings, model_id, timeout_seconds, timeout_seconds, 1, max_tokens=64)


def build_agent_model(settings: Settings, attempts: int = AGENT_RETRIES) -> BedrockModel:
    """The text model every feedback agent uses; `attempts` is botocore's max_attempts: the retries after the first call."""
    return _bedrock(settings, settings.text_model, DEFAULT_TIMEOUT_SECONDS, AGENT_READ_TIMEOUT_SECONDS, attempts,
                    temperature=AGENT_TEMPERATURE, max_tokens=AGENT_MAX_TOKENS)


def with_max_tokens(model: Any, max_tokens: int) -> Any:
    """A copy of a Bedrock model that asks for `max_tokens` (Bedrock charges the daily quota by that cap, not by what is generated).

    Anything that isn't a BedrockModel (a scripted model in tests) is returned unchanged.
    """
    if not isinstance(model, BedrockModel):
        return model
    capped = copy.copy(model)
    capped.config = {**model.config, "max_tokens": max_tokens}
    return capped
