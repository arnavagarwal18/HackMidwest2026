"""Expired or invalid AWS credentials: the run goes straight to the rule fallback with one model call, never retried."""
import json
import logging

import pytest
from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError, CredentialRetrievalError, NoCredentialsError, TokenRetrievalError
from strands.agent import agent as strands_agent
from strands.types.exceptions import ModelThrottledException

from app import store
from app.agents import ai_run
from app.agents.config import Settings
from app.agents.credentials import CREDENTIALS_EXPIRED_LINE, is_credential_error
from app.agents.model import AGENT_RETRIES, build_agent_model
from tests.fake_model import ScriptedModel, text_turn
from tests.feedback_helpers import add_diagnosed_take
from tests.test_run_ai import BRIEF, OVERVIEW, ai_on, feedback_of, use_script  # noqa: F401  (ai_on is an autouse fixture)

SECRET_MESSAGE = "placeholder-secret-message-9f3"


def client_error(code: str, message: str = SECRET_MESSAGE) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": message}}, "ConverseStream")


CREDENTIAL_ERRORS = [
    client_error("ExpiredTokenException"),
    client_error("ExpiredToken"),
    client_error("UnrecognizedClientException"),
    client_error("InvalidClientTokenId"),
    client_error("InvalidSignatureException"),
    client_error("AccessDeniedException", f"The security token included in the request is expired {SECRET_MESSAGE}"),
    NoCredentialsError(),
    TokenRetrievalError(provider="sso", error_msg=SECRET_MESSAGE),
    CredentialRetrievalError(provider="sso", error_msg=SECRET_MESSAGE),
]
CREDENTIAL_IDS = [
    "ExpiredTokenException", "ExpiredToken", "UnrecognizedClientException", "InvalidClientTokenId",
    "InvalidSignatureException", "AccessDeniedException_token", "NoCredentialsError", "TokenRetrievalError", "CredentialRetrievalError",
]


def warnings_in(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.getMessage() == CREDENTIALS_EXPIRED_LINE]


def assert_learner_sees_the_normal_fallback(feedback: dict, plan: dict) -> None:
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "model_error")
    assert feedback["sentences"][0]["mode"] == "fallback" and len(plan["exercises"]) == 3
    assert SECRET_MESSAGE not in json.dumps([feedback, plan])


@pytest.mark.parametrize("error", CREDENTIAL_ERRORS, ids=CREDENTIAL_IDS)
def test_a_credential_error_falls_back_with_one_model_call_and_the_warning(sessions_root, fixture_data, monkeypatch, caplog, error):
    monkeypatch.setattr(strands_agent, "MAX_ATTEMPTS", 6)
    model = use_script(monkeypatch, error)
    feedback, plan = feedback_of(fixture_data)
    assert_learner_sees_the_normal_fallback(feedback, plan)
    assert model.calls == 1
    assert warnings_in(caplog) == [CREDENTIALS_EXPIRED_LINE]
    assert SECRET_MESSAGE not in caplog.text


def test_a_credential_error_in_the_coach_stops_the_orchestrator_too(sessions_root, fixture_data, monkeypatch, caplog):
    model = use_script(monkeypatch, OVERVIEW, BRIEF, client_error("ExpiredTokenException"))
    feedback, plan = feedback_of(fixture_data)
    assert_learner_sees_the_normal_fallback(feedback, plan)
    assert model.calls == 3  # the Orchestrator twice (overview, hand-over) and the Coach once; no model call after the failure
    assert warnings_in(caplog) == [CREDENTIALS_EXPIRED_LINE]
    assert SECRET_MESSAGE not in caplog.text


def test_a_credential_error_is_found_under_a_wrapper():
    try:
        try:
            raise client_error("ExpiredToken")
        except ClientError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError as outer:
        assert is_credential_error(outer)


@pytest.mark.parametrize("error", [
    client_error("AccessDeniedException", "You don't have access to the model with the specified model ID."),
    client_error("ThrottlingException"),
    client_error("ValidationException"),
    ModelThrottledException("slow down"),
    ValueError("boom"),
], ids=lambda e: type(e).__name__)
def test_other_errors_are_not_credential_errors(error):
    assert not is_credential_error(error)


def test_a_throttling_error_is_still_retried_by_strands_and_logs_no_credential_line(sessions_root, fixture_data, monkeypatch, caplog):
    monkeypatch.setattr(strands_agent, "MAX_ATTEMPTS", 2)
    monkeypatch.setattr(strands_agent, "INITIAL_DELAY", 0)
    model = use_script(monkeypatch, ModelThrottledException("slow down"), ModelThrottledException("slow down"))
    feedback, _ = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "model_error")
    assert model.calls == 2
    assert warnings_in(caplog) == []


def test_the_run_error_class_is_kept_for_the_trace(sessions_root, fixture_data, monkeypatch):
    use_script(monkeypatch, client_error("ExpiredTokenException"))
    session_id, take_id = add_diagnosed_take(fixture_data)
    from app.agents import run
    feedback_id = run.run_feedback(session_id, take_id)
    trace = json.loads((store.session_dir(session_id) / f"{feedback_id}_trace.json").read_text(encoding="utf-8"))
    assert any("ClientError" in event["detail"] for event in trace if event["event"] == "fallback")


@pytest.mark.parametrize("code, status", [
    ("ExpiredTokenException", 400), ("ExpiredToken", 400), ("UnrecognizedClientException", 403),
    ("InvalidClientTokenId", 403), ("InvalidSignatureException", 403), ("AccessDeniedException", 403),
])
def test_botocore_does_not_retry_these_codes(monkeypatch, code, status):
    """The real Bedrock client, with the agents' retry settings and a canned HTTP answer: it sends the request once."""
    for name, value in {"AWS_ACCESS_KEY_ID": "placeholder-id", "AWS_SECRET_ACCESS_KEY": "placeholder-key", "AWS_SESSION_TOKEN": "placeholder-token"}.items():
        monkeypatch.setenv(name, value)
    settings = Settings(region="us-east-1", text_model="text-model-id", vision_model="vision-model-id", aws_profile="", ai_enabled=True)
    client, sent = build_agent_model(settings, attempts=AGENT_RETRIES).client, []

    class Body:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def stream(self, **kwargs):
            yield self.data

        def read(self, *args):
            return self.data

    def canned_answer(request, **kwargs):
        sent.append(request.url)
        body = json.dumps({"__type": code, "message": SECRET_MESSAGE}).encode()
        return AWSResponse(request.url, status, {"x-amzn-errortype": code, "content-type": "application/json"}, Body(body))

    client.meta.events.register("before-send", canned_answer)
    with pytest.raises(ClientError) as raised:
        client.converse_stream(modelId="text-model-id", messages=[{"role": "user", "content": [{"text": "hi"}]}])
    assert raised.value.response["Error"]["Code"] == code
    assert len(sent) == 1
