import pytest
from botocore.exceptions import ClientError, NoCredentialsError, ReadTimeoutError, TokenRetrievalError

from app.agents import config, smoke
from app.agents.config import ConfigError, Settings, parse_settings
from app.agents.credentials import CREDENTIALS_EXPIRED_LINE
from app.agents.smoke_errors import describe_failure

SETTING_NAMES = ["BEDROCK_REGION", "BEDROCK_TEXT_MODEL", "BEDROCK_VISION_MODEL", "AWS_PROFILE", "AI_ENABLED"]
FULL_ENV = {
    "BEDROCK_REGION": "us-east-1",
    "BEDROCK_TEXT_MODEL": "text-model-id",
    "BEDROCK_VISION_MODEL": "vision-model-id",
    "AWS_PROFILE": "hackmidwest",
    "AI_ENABLED": "true",
}


@pytest.fixture
def clean_settings(tmp_path, monkeypatch):
    """No .env file and none of the AI settings in the environment."""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing.env")
    monkeypatch.setattr(smoke, "LOG_FILE", tmp_path / "smoke.log")
    config.get_settings.cache_clear()
    yield monkeypatch
    config.get_settings.cache_clear()


def test_parse_full_settings():
    assert parse_settings(FULL_ENV) == Settings(
        region="us-east-1",
        text_model="text-model-id",
        vision_model="vision-model-id",
        aws_profile="hackmidwest",
        ai_enabled=True,
    )


@pytest.mark.parametrize("raw, expected", [("true", True), ("TRUE", True), ("1", True), ("false", False), ("False", False), ("", False)])
def test_ai_enabled_values(raw, expected):
    env = {**FULL_ENV, "AI_ENABLED": raw}
    assert parse_settings(env).ai_enabled is expected


def test_ai_enabled_defaults_to_false_when_missing():
    settings = parse_settings({})
    assert settings.ai_enabled is False
    assert settings.region == ""


def test_ai_enabled_rejects_unknown_value():
    with pytest.raises(ConfigError, match="AI_ENABLED must be true or false"):
        parse_settings({**FULL_ENV, "AI_ENABLED": "maybe"})


@pytest.mark.parametrize("missing", ["BEDROCK_REGION", "BEDROCK_TEXT_MODEL", "BEDROCK_VISION_MODEL"])
def test_enabled_without_required_setting_names_it(missing):
    env = {**FULL_ENV, missing: ""}
    with pytest.raises(ConfigError, match=missing):
        parse_settings(env)


def test_disabled_without_models_is_fine():
    parse_settings({"AI_ENABLED": "false"})


def test_settings_are_frozen():
    with pytest.raises(AttributeError):
        parse_settings(FULL_ENV).region = "elsewhere"


def test_get_settings_reads_env_file_and_environment_wins(clean_settings, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("BEDROCK_REGION=us-west-2\nBEDROCK_TEXT_MODEL=t\nBEDROCK_VISION_MODEL=v\nAI_ENABLED=true\n")
    clean_settings.setattr(config, "ENV_FILE", env_file)
    clean_settings.setenv("BEDROCK_REGION", "eu-west-1")
    settings = config.get_settings()
    assert settings.region == "eu-west-1"
    assert settings.text_model == "t"
    assert settings.ai_enabled is True


def test_smoke_exits_1_when_settings_absent(clean_settings, capsys):
    clean_settings.setattr(smoke, "_ask", lambda *args: pytest.fail("must not call Bedrock without settings"))
    assert smoke.main() == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert out[0].startswith("FAILED:") and "AI_ENABLED" in out[0] and "backend/.env" in out[0]


def test_smoke_exits_1_naming_missing_model(clean_settings, capsys):
    clean_settings.setenv("AI_ENABLED", "true")
    clean_settings.setenv("BEDROCK_REGION", "us-east-1")
    assert smoke.main() == 1
    assert "BEDROCK_TEXT_MODEL" in capsys.readouterr().out


def test_smoke_reports_missing_credentials_once(clean_settings, capsys):
    for name, value in FULL_ENV.items():
        clean_settings.setenv(name, value)

    def no_credentials(*args):
        raise NoCredentialsError()

    clean_settings.setattr(smoke, "_ask", no_credentials)
    assert smoke.main() == 1
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert "aws sts get-caller-identity --profile hackmidwest" in out[0]


@pytest.mark.parametrize("error", [
    ClientError({"Error": {"Code": "ExpiredTokenException", "Message": "expired"}}, "ConverseStream"),
    ClientError({"Error": {"Code": "InvalidSignatureException", "Message": "bad"}}, "ConverseStream"),
    TokenRetrievalError(provider="sso", error_msg="expired"),
], ids=["ExpiredTokenException", "InvalidSignatureException", "TokenRetrievalError"])
def test_smoke_prints_the_expired_credentials_line(clean_settings, capsys, error):
    for name, value in FULL_ENV.items():
        clean_settings.setenv(name, value)

    def expired(*args):
        raise error

    clean_settings.setattr(smoke, "_ask", expired)
    assert smoke.main() == 1
    [line] = capsys.readouterr().out.strip().splitlines()
    assert line.startswith(f"FAILED: {CREDENTIALS_EXPIRED_LINE}")


def test_smoke_succeeds_and_prints_both_replies(clean_settings, capsys):
    for name, value in FULL_ENV.items():
        clean_settings.setenv(name, value)
    clean_settings.setattr(smoke, "_ask", lambda settings, model_id, content: f"reply from {model_id}")
    assert smoke.main() == 0
    out = capsys.readouterr().out
    assert "reply from text-model-id" in out and "reply from vision-model-id" in out


def test_tiny_png_is_a_valid_png():
    png = smoke.tiny_red_png()
    assert png.startswith(b"\x89PNG\r\n\x1a\n") and png.endswith(b"IEND\xaeB`\x82")


def _failure_line(exc):
    return describe_failure(exc, "text model", "text-model-id", parse_settings(FULL_ENV))


def test_access_denied_points_to_model_access():
    exc = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "Converse")
    line = _failure_line(exc)
    assert "refused access" in line and "Bedrock console" in line


def test_timeout_is_explained():
    assert "10 seconds" in _failure_line(ReadTimeoutError(endpoint_url="https://example.invalid"))


def test_wrapped_cause_is_recognised():
    try:
        try:
            raise NoCredentialsError()
        except NoCredentialsError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert "credentials" in _failure_line(outer)


def test_unknown_failure_is_generic_but_names_the_error():
    assert "ValueError: boom" in _failure_line(ValueError("boom"))
