import json

import pytest

from app import store


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"]


def new_session_id(client, instrument="violin"):
    return client.post("/sessions", json={"instrument": instrument}).json()["session_id"]


def test_create_violin_session(client, sessions_root):
    response = client.post("/sessions", json={"instrument": "violin"})
    assert response.status_code == 201
    body = response.json()
    assert body["instrument"] == "violin"
    assert len(body["session_id"]) == 32
    saved = json.loads((sessions_root / body["session_id"] / "session.json").read_text())
    assert saved["score_status"] == "none"


def test_unknown_instrument_is_bad_request(client):
    assert_error(client.post("/sessions", json={"instrument": "piano"}), 422, "bad_request")


def test_missing_body_is_bad_request(client):
    assert_error(client.post("/sessions", json={}), 422, "bad_request")


def test_get_session(client):
    session_id = new_session_id(client, "trumpet")
    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "instrument": "trumpet",
        "score_status": "none",
        "has_calibration": False,
        "take_ids": [],
    }


def test_get_unknown_session(client):
    assert_error(client.get("/sessions/doesnotexist"), 404, "session_not_found")


def test_get_session_with_path_characters_is_not_found(client):
    assert_error(client.get("/sessions/..%5Cx"), 404, "session_not_found")


def test_storage_failure_is_storage_error(client, sessions_root):
    sessions_root.parent.mkdir(parents=True, exist_ok=True)
    sessions_root.write_text("a file where the sessions folder should be")
    assert_error(client.post("/sessions", json={"instrument": "violin"}), 500, "storage_error")


def test_update_persists_and_reloads(client):
    session_id = new_session_id(client)
    store.update(session_id, "calibration", {"a4": 440})
    store._sessions.clear()
    assert client.get(f"/sessions/{session_id}").json()["has_calibration"] is True


def test_update_rejects_unknown_key(client):
    session_id = new_session_id(client)
    with pytest.raises(ValueError):
        store.update(session_id, "nonsense", 1)


def test_frontend_served_at_root(client):
    assert client.get("/").status_code == 200
