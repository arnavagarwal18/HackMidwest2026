import threading
from dataclasses import replace
from pathlib import Path

import pytest

from app.agents.config import ConfigError, Settings
from app.score import reader_agent
from app.score.compare import NO_READING_WARNING, compare_bars
from app.score.reading import Reading
from tests.test_score_compare import make_score

SETTINGS_ON = Settings(region="us-east-1", text_model="text-model", vision_model="vision-model", aws_profile="", ai_enabled=True)
GOOD_ANSWER = {"bars": [{"bar": 1, "notes": [{"name": "E5", "length": "quarter"}]}]}


@pytest.fixture
def image(tmp_path) -> Path:
    path = tmp_path / "cleaned.png"
    path.write_bytes(b"\x89PNG not really")
    return path


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(reader_agent, "get_settings", lambda: SETTINGS_ON)


def stub_model(monkeypatch, answer=None, error=None):
    def fake(settings, image_path, cancel, timeout_s):
        if error:
            raise error
        return answer

    monkeypatch.setattr(reader_agent, "_ask_model", fake)


def assert_no_reading_gives_not_double_checked(reading):
    assert reading is None
    result = compare_bars(make_score(), reading)
    assert result.double_checked is False
    assert result.warnings == [NO_READING_WARNING]


def test_valid_answer_becomes_a_reading(ai_on, monkeypatch, image):
    stub_model(monkeypatch, answer=GOOD_ANSWER)
    reading = reader_agent.read_score(image)
    assert reading == Reading.model_validate(GOOD_ANSWER)


def test_ai_disabled_gives_no_reading_without_calling_the_model(monkeypatch, image):
    monkeypatch.setattr(reader_agent, "get_settings", lambda: replace(SETTINGS_ON, ai_enabled=False))
    stub_model(monkeypatch, error=AssertionError("model must not be called"))
    assert_no_reading_gives_not_double_checked(reader_agent.read_score(image))


def test_bad_settings_give_no_reading(monkeypatch, image):
    def broken():
        raise ConfigError("AI_ENABLED is true but BEDROCK_VISION_MODEL is empty.")

    monkeypatch.setattr(reader_agent, "get_settings", broken)
    assert_no_reading_gives_not_double_checked(reader_agent.read_score(image))


@pytest.mark.parametrize(
    "answer",
    [None, {"rows": []}, {"bars": "none"}, {"bars": [{"bar": "one", "notes": []}]}, {"bars": [{"bar": 1, "notes": [{"name": "E5"}]}]}],
)
def test_output_not_fitting_the_schema_gives_no_reading(ai_on, monkeypatch, image, answer):
    stub_model(monkeypatch, answer=answer)
    assert_no_reading_gives_not_double_checked(reader_agent.read_score(image))


def test_bedrock_error_gives_no_reading(ai_on, monkeypatch, image):
    stub_model(monkeypatch, error=RuntimeError("AccessDeniedException: no access to the model"))
    assert_no_reading_gives_not_double_checked(reader_agent.read_score(image))


def test_timeout_gives_no_reading_and_cancels_the_call(ai_on, monkeypatch, image):
    saw_cancel = threading.Event()

    def hang(settings, image_path, cancel, timeout_s):
        if cancel.wait(5):
            saw_cancel.set()

    monkeypatch.setattr(reader_agent, "_ask_model", hang)
    assert_no_reading_gives_not_double_checked(reader_agent.read_score(image, timeout_s=0.1))
    assert saw_cancel.wait(2)


def test_ask_model_sends_the_image_and_asks_for_a_reading(monkeypatch, image):
    calls = {}

    class FakeModel:
        def update_config(self, **config):
            calls["config"] = config

    class FakeAgent:
        def __init__(self, model, callback_handler):
            calls["model"] = model

        def __call__(self, content, structured_output_model, cancel_signal):
            calls.update(content=content, schema=structured_output_model)
            return type("Result", (), {"structured_output": Reading.model_validate(GOOD_ANSWER)})()

    monkeypatch.setattr(reader_agent, "Agent", FakeAgent)
    monkeypatch.setattr(
        reader_agent, "build_bedrock_model", lambda settings, model_id, timeout_seconds: calls.update(model_id=model_id) or FakeModel()
    )
    result = reader_agent._ask_model(SETTINGS_ON, image, threading.Event(), 30)
    assert result == Reading.model_validate(GOOD_ANSWER)
    assert calls["model_id"] == "vision-model"
    assert calls["schema"] is Reading
    assert calls["config"]["max_tokens"] > 64
    assert calls["content"][1]["image"]["format"] == "png"
    assert calls["content"][1]["image"]["source"]["bytes"] == image.read_bytes()


def test_unsupported_image_type_gives_no_reading(ai_on, tmp_path):
    path = tmp_path / "scan.tiff"
    path.write_bytes(b"x")
    assert reader_agent.read_score(path) is None
