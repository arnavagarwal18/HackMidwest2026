"""Turns Bedrock/AWS failures into one plain-words line saying what to fix."""
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    PartialCredentialsError,
    ProfileNotFound,
    ReadTimeoutError,
    SSOError,
    TokenRetrievalError,
)

from app.agents.config import ConfigError, Settings

CONFIG_FIX = "Setup step: edit backend/.env (copy backend/.env.example first if you have no backend/.env)."
CREDENTIAL_ERRORS = (NoCredentialsError, PartialCredentialsError, ProfileNotFound, TokenRetrievalError, SSOError)
TIMEOUT_ERRORS = (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError)
ACCESS_DENIED_CODES = {"AccessDeniedException", "UnrecognizedClientException", "ExpiredTokenException", "ExpiredToken"}


def _chain(exc: BaseException):
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def describe_config_error(exc: ConfigError) -> str:
    return f"{exc} {CONFIG_FIX}"


def _profile_check(settings: Settings) -> str:
    profile = f" --profile {settings.aws_profile}" if settings.aws_profile else ""
    return f"aws sts get-caller-identity{profile}"


def _explain(exc: BaseException, step: str, model_id: str, settings: Settings) -> str | None:
    if isinstance(exc, ConfigError):
        return describe_config_error(exc)
    if isinstance(exc, CREDENTIAL_ERRORS):
        return (
            f"AWS credentials were not found or have expired. Run `{_profile_check(settings)}` to check; "
            "if it fails, sign in again (aws sso login) or set up the profile (aws configure)."
        )
    if isinstance(exc, TIMEOUT_ERRORS):
        return (
            f"Bedrock did not answer the {step} within 10 seconds. Check your internet connection and that "
            f"BEDROCK_REGION ({settings.region}) is a region where Bedrock runs."
        )
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ACCESS_DENIED_CODES:
            return (
                f"AWS refused access to {model_id} ({code}). Run `{_profile_check(settings)}` to confirm the profile, "
                f"then enable access to that model in the Bedrock console for region {settings.region}."
            )
        if code in {"ResourceNotFoundException", "ValidationException"}:
            return (
                f"Bedrock does not accept the {step} ID '{model_id}' ({code}). "
                "Check the model ID in backend/.env and that it is enabled in your region."
            )
    return None


def describe_failure(exc: BaseException, step: str, model_id: str, settings: Settings) -> str:
    """One line for the first recognised cause in the exception chain, else a generic line."""
    for cause in _chain(exc):
        line = _explain(cause, step, model_id, settings)
        if line:
            return line
    return f"The {step} check failed unexpectedly ({type(exc).__name__}: {exc}). Tell the team."
