import sys
import time
from pathlib import Path

import pytest

from app.score import compare, homr_runner, reader_agent, scan_job
from tests.photo_factory import encode, staff_image

FIXTURES = Path(__file__).parent / "fixtures"
ODE_TO_JOY = Path(__file__).parents[1] / "app" / "score" / "builtins" / "ode_to_joy.musicxml"
STUB = FIXTURES / "stub_homr.py"
MB = 1024 * 1024


@pytest.fixture(autouse=True)
def no_reader(monkeypatch):
    """These tests are about the photo scan itself: the Score reader gives no reading (and never calls Bedrock)."""
    monkeypatch.setattr(reader_agent, "read_score", lambda image_path, timeout_s=30: None)


@pytest.fixture
def stub_homr(monkeypatch):
    """Replace the homr command with the stub script; returns a function choosing its mode."""
    monkeypatch.setattr(homr_runner, "homr_command", lambda image: [sys.executable, str(STUB), str(image)])
    monkeypatch.setenv("STUB_HOMR_MUSICXML", str(ODE_TO_JOY))

    def choose(mode, musicxml=None):
        monkeypatch.setenv("STUB_HOMR_MODE", mode)
        if musicxml:
            monkeypatch.setenv("STUB_HOMR_MUSICXML", str(musicxml))

    return choose


@pytest.fixture
def session_id(client):
    return client.post("/sessions", json={"instrument": "violin"}).json()["session_id"]


def photo_png():
    return encode(staff_image())


def post_photo(client, session_id, data=None, name="photo.png"):
    return client.post(f"/sessions/{session_id}/score/photo", files={"file": (name, photo_png() if data is None else data)})


def status(client, session_id):
    return client.get(f"/sessions/{session_id}/score/status").json()


def wait_until_done(client, session_id, seconds=20):
    deadline = time.time() + seconds
    while time.time() < deadline:
        body = status(client, session_id)
        if body["score_status"] != "scanning":
            return body
        time.sleep(0.05)
    raise AssertionError("the scan never finished")


def assert_error(response, status_code, code):
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code


def test_photo_scan_goes_from_scanning_to_scanned(client, session_id, stub_homr):
    stub_homr("slow")
    response = post_photo(client, session_id)
    assert response.status_code == 202
    assert response.json() == {"score_status": "scanning"}
    assert status(client, session_id)["score_status"] == "scanning"

    done = wait_until_done(client, session_id)
    assert done == {
        "score_status": "scanned",
        "score_error": None,
        "score_error_message": None,
        "bars": 16,
        "doubtful_bars": [],
        "double_checked": False,
        "warnings": [compare.NO_READING_WARNING],
    }
    assert client.get(f"/sessions/{session_id}/score").status_code == 200  # the scanned score can be read back


def test_scanned_photo_score_can_be_confirmed(client, session_id, stub_homr):
    stub_homr("ok")
    post_photo(client, session_id)
    wait_until_done(client, session_id)
    assert client.post(f"/sessions/{session_id}/score/confirm", json={}).json()["bars"] == 16


def test_rescan_before_confirming_replaces_the_result(client, session_id, stub_homr):
    stub_homr("ok", FIXTURES / "two_parts.musicxml")
    post_photo(client, session_id)
    first = wait_until_done(client, session_id)
    stub_homr("ok", ODE_TO_JOY)
    assert post_photo(client, session_id).status_code == 202
    second = wait_until_done(client, session_id)
    assert second["bars"] == 16 and first["bars"] != 16


def test_homr_crash_is_scan_failed(client, session_id, stub_homr):
    stub_homr("fail")
    post_photo(client, session_id)
    done = wait_until_done(client, session_id)
    assert (done["score_status"], done["score_error"], done["bars"]) == ("failed", "scan_failed", None)
    assert done["score_error_message"] == scan_job.SCAN_MESSAGES["scan_failed"]
    assert "sharper, straighter photo" in done["score_error_message"]


def test_homr_writing_nothing_is_scan_failed(client, session_id, stub_homr):
    stub_homr("silent")
    post_photo(client, session_id)
    assert wait_until_done(client, session_id)["score_error"] == "scan_failed"


def test_homr_past_the_limit_is_killed_and_scan_timeout(client, session_id, stub_homr, monkeypatch):
    stub_homr("hang")
    monkeypatch.setenv(homr_runner.TIMEOUT_ENV, "2")
    started = time.time()
    post_photo(client, session_id)
    done = wait_until_done(client, session_id)
    assert (done["score_status"], done["score_error"]) == ("failed", "scan_timeout")
    assert done["score_error_message"].startswith("Reading the photo took too long.")
    assert time.time() - started < 15  # the stub sleeps 30 s, so it was killed


def test_musicxml_without_notes_is_no_notes(client, session_id, stub_homr):
    stub_homr("ok", FIXTURES / "no_notes.musicxml")
    post_photo(client, session_id)
    done = wait_until_done(client, session_id)
    assert (done["score_status"], done["score_error"]) == ("failed", "no_notes")
    assert done["score_error_message"] == "No notes found in this photo. Is the whole staff inside the crop?"


def test_unparseable_musicxml_is_scan_failed(client, session_id, stub_homr):
    stub_homr("ok", FIXTURES / "broken.musicxml")
    post_photo(client, session_id)
    assert wait_until_done(client, session_id)["score_error"] == "scan_failed"


def test_unreadable_image_content_is_scan_failed(client, session_id, stub_homr):
    stub_homr("ok")
    post_photo(client, session_id, data=b"\x89PNG\r\n\x1a\n not really a png")
    assert wait_until_done(client, session_id)["score_error"] == "scan_failed"


def test_failed_scan_can_be_retried(client, session_id, stub_homr):
    stub_homr("fail")
    post_photo(client, session_id)
    wait_until_done(client, session_id)
    stub_homr("ok")
    assert post_photo(client, session_id).status_code == 202
    assert wait_until_done(client, session_id)["score_status"] == "scanned"


def test_photo_while_scanning_is_wrong_state(client, session_id, stub_homr):
    stub_homr("slow")
    post_photo(client, session_id)
    assert_error(post_photo(client, session_id), 409, "wrong_state")
    wait_until_done(client, session_id)


def test_photo_after_confirm_is_wrong_state(client, session_id):
    client.post(f"/sessions/{session_id}/score/file", json={"builtin": "ode_to_joy"})
    client.post(f"/sessions/{session_id}/score/confirm", json={})
    assert_error(post_photo(client, session_id), 409, "wrong_state")


def test_non_image_is_415(client, session_id):
    assert_error(post_photo(client, session_id, data=b"%PDF-1.4 hello", name="photo.png"), 415, "unsupported_type")
    assert status(client, session_id)["score_status"] == "none"


def test_photo_over_15_mb_is_413(client, session_id):
    assert_error(post_photo(client, session_id, data=b"\xff\xd8\xff" + b"0" * (15 * MB)), 413, "file_too_large")
    assert status(client, session_id)["score_status"] == "none"


def test_photo_without_a_file_is_422(client, session_id):
    assert_error(client.post(f"/sessions/{session_id}/score/photo", data={"x": "y"}), 422, "bad_request")


def test_unknown_session_is_404(client):
    assert_error(post_photo(client, "nosuchsession"), 404, "session_not_found")
    assert_error(client.get("/sessions/nosuchsession/score/status"), 404, "session_not_found")


def test_status_before_any_scan(client, session_id):
    assert status(client, session_id) == {
        "score_status": "none",
        "score_error": None,
        "score_error_message": None,
        "bars": None,
        "doubtful_bars": [],
        "double_checked": False,
        "warnings": [],
    }


def test_invalid_timeout_setting_falls_back_to_300(monkeypatch):
    monkeypatch.setenv(homr_runner.TIMEOUT_ENV, "soon")
    assert homr_runner.timeout_seconds() == 300.0
    monkeypatch.delenv(homr_runner.TIMEOUT_ENV)
    assert homr_runner.timeout_seconds() == 300.0
