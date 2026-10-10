"""Builds Bedrock models for Strands agents from Settings."""
import boto3
from botocore.config import Config as BotocoreConfig
from strands.models import BedrockModel

from app.agents.config import Settings

DEFAULT_TIMEOUT_SECONDS = 10


def build_bedrock_model(settings: Settings, model_id: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> BedrockModel:
    """A BedrockModel using the AWS CLI profile named in settings (or the default AWS credential chain)."""
    session = boto3.Session(profile_name=settings.aws_profile or None, region_name=settings.region)
    client_config = BotocoreConfig(
        connect_timeout=timeout_seconds,
        read_timeout=timeout_seconds,
        retries={"max_attempts": 1},
    )
    return BedrockModel(model_id=model_id, boto_session=session, boto_client_config=client_config, max_tokens=64)
