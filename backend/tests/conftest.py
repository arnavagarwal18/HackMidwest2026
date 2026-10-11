import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import store
from app.agents.context import build_context
from app.main import app

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "diagnosis_fixture.json"


@pytest.fixture(autouse=True)
def ai_off_unless_a_test_turns_it_on(monkeypatch):
    """The process environment wins over backend/.env, so a developer's .env with AI_ENABLED=true never sends a test to Bedrock."""
    monkeypatch.setenv("AI_ENABLED", "false")


@pytest.fixture
def sessions_root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SESSIONS_ROOT", tmp_path / "sessions")
    store._sessions.clear()
    yield tmp_path / "sessions"
    store._sessions.clear()


@pytest.fixture
def client(sessions_root):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def fixture_data():
    return json.loads(FIXTURE_PATH.read_text())


@pytest.fixture
def check_ctx(fixture_data):
    return build_context(
        fixture_data["session_id"],
        fixture_data["take_id"],
        get_diagnosis=lambda s, t: fixture_data["diagnosis"],
        get_form=lambda s, t: fixture_data["form"],
        get_earlier_takes=lambda s, t: fixture_data["history"],
    )
