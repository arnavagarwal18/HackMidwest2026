import threading

import pytest

from app import store
from app.agents import run
from tests.feedback_helpers import add_diagnosed_take


@pytest.fixture(autouse=True)
def ai_off(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: False)


def url(session_id, take_id="t1"):
    return f"/sessions/{session_id}/takes/{take_id}/feedback"


def test_get_is_409_until_the_take_is_done_then_200_with_feedback_and_plan(client, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data)
    early = client.get(url(session_id, take_id))
    assert (early.status_code, early.json()) == (409, {"error": {"code": "wrong_state", "message": "Feedback not ready."}})
    assert client.post(url(session_id, take_id), json={}).status_code == 200
    store.update(session_id, "takes", {take_id: {**store.get(session_id).takes[take_id], "status": "processing"}})
    assert client.get(url(session_id, take_id)).status_code == 409
    store.update(session_id, "takes", {take_id: {**store.get(session_id).takes[take_id], "status": "done"}})
    body = client.get(url(session_id, take_id)).json()
    assert (body["id"], body["take_id"], body["mode"], body["fallback_reason"]) == ("fb1", "t1", "fallback", "disabled")
    assert body["plan"]["id"] == "pl1" and len(body["plan"]["exercises"]) == 3


def test_get_is_409_when_a_done_take_has_no_feedback(client, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    assert client.get(url(session_id, take_id)).status_code == 409


def test_get_returns_the_latest_feedback_of_the_take(client, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    for _ in range(10):
        run.run_feedback(session_id, take_id)
    assert client.get(url(session_id, take_id)).json()["id"] == "fb10"


@pytest.mark.parametrize("method", ["get", "post"])
def test_unknown_session_and_take_are_404(client, fixture_data, method):
    session_id, _ = add_diagnosed_take(fixture_data, status="done")
    call = getattr(client, method)
    missing_session = call(url("nosuchsession"))
    assert (missing_session.status_code, missing_session.json()["error"]["code"]) == (404, "session_not_found")
    missing_take = call(url(session_id, "t9"))
    assert (missing_take.status_code, missing_take.json()["error"]["code"]) == (404, "take_not_found")


@pytest.mark.parametrize("status, form_status", [("processing", "none"), ("transcribed", "none"), ("failed", "none"), ("diagnosed", "processing")])
def test_post_is_409_before_the_take_is_diagnosed(client, fixture_data, status, form_status):
    session_id, take_id = add_diagnosed_take(fixture_data, status=status)
    store.update(session_id, "takes", {take_id: {**store.get(session_id).takes[take_id], "form_status": form_status}})
    response = client.post(url(session_id, take_id), json={})
    assert (response.status_code, response.json()["error"]["code"]) == (409, "wrong_state")
    assert store.get(session_id).feedback == {}


def test_post_runs_feedback_again_and_returns_the_new_record(client, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    first, second = (client.post(url(session_id, take_id), json={}).json() for _ in range(2))
    assert (first["id"], second["id"], second["plan"]["id"]) == ("fb1", "fb2", "pl2")
    assert client.get(url(session_id, take_id)).json()["id"] == "fb2"


def test_post_without_a_body_is_accepted(client, fixture_data):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    assert client.post(url(session_id, take_id)).status_code == 200


def test_a_second_post_while_one_is_running_gets_409(client, fixture_data, monkeypatch):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    started, release = threading.Event(), threading.Event()

    def slow_settings():
        started.set()
        release.wait(5)
        return False

    monkeypatch.setattr(run, "ai_enabled", slow_settings)
    first = {}
    worker = threading.Thread(target=lambda: first.update(response=client.post(url(session_id, take_id), json={})))
    worker.start()
    assert started.wait(5)
    second = client.post(url(session_id, take_id), json={})
    assert (second.status_code, second.json()["error"]) == (409, {"code": "wrong_state", "message": "Feedback already running."})
    release.set()
    worker.join(5)
    assert first["response"].status_code == 200
    assert client.post(url(session_id, take_id), json={}).status_code == 200  # the lock was released


def test_post_reports_a_storage_failure(client, fixture_data, monkeypatch):
    session_id, take_id = add_diagnosed_take(fixture_data, status="done")
    real_update = store.update

    def failing_update(sid, key, value):
        if key in ("feedback", "plans"):
            raise OSError("disk full")
        return real_update(sid, key, value)

    monkeypatch.setattr(store, "update", failing_update)
    response = client.post(url(session_id, take_id), json={})
    assert (response.status_code, response.json()["error"]["code"]) == (500, "storage_error")
    assert store.get(session_id).takes[take_id]["status"] == "failed"
