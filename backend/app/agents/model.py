"""Builds Bedrock models for Strands agents from Settings."""
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


def build_agent_model(settings: Settings) -> BedrockModel:
    """The text model every feedback agent uses."""
    return _bedrock(settings, settings.text_model, DEFAULT_TIMEOUT_SECONDS, AGENT_READ_TIMEOUT_SECONDS, AGENT_RETRIES,
                    temperature=AGENT_TEMPERATURE, max_tokens=AGENT_MAX_TOKENS)
