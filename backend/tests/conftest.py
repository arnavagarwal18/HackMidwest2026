import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app


@pytest.fixture
def sessions_root(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SESSIONS_ROOT", tmp_path / "sessions")
    store._sessions.clear()
    yield tmp_path / "sessions"
    store._sessions.clear()


@pytest.fixture
def client(sessions_root):
    return TestClient(app, raise_server_exceptions=False)
