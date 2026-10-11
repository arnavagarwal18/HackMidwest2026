from app.agents.config import Settings
from app.agents.model import build_agent_model, build_bedrock_model, with_max_tokens
from tests.fake_model import ScriptedModel

SETTINGS = Settings(region="test-region", text_model="test-text", vision_model="test-vision", aws_profile="", ai_enabled=True)


def test_the_agent_model_follows_the_bedrock_contract():
    model = build_agent_model(SETTINGS)
    config = model.get_config()
    assert (config["model_id"], config["temperature"], config["max_tokens"]) == ("test-text", 0.2, 2000)
    client_config = model.client.meta.config
    assert client_config.read_timeout == 20
    assert client_config.retries["total_max_attempts"] == 3  # 2 retries
    assert model.client.meta.region_name == "test-region"


def test_other_callers_keep_their_timeout_and_can_still_raise_the_token_limit():
    model = build_bedrock_model(SETTINGS, "other-model", timeout_seconds=7)
    model.update_config(max_tokens=4096)
    assert model.client.meta.config.read_timeout == 7
    assert model.get_config()["max_tokens"] == 4096


def test_with_max_tokens_caps_a_copy_and_leaves_the_shared_model_alone():
    shared = build_agent_model(SETTINGS)
    capped = with_max_tokens(shared, 900)
    assert capped.get_config()["max_tokens"] == 900
    assert capped.get_config()["model_id"] == "test-text"
    assert shared.get_config()["max_tokens"] == 2000
    assert capped.client is shared.client


def test_with_max_tokens_leaves_a_non_bedrock_model_unchanged():
    model = ScriptedModel([])
    assert with_max_tokens(model, 900) is model
