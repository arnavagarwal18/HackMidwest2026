import logging
from pathlib import Path

import pytest

from app import store
from app.score.model import Score

FIXTURES = Path(__file__).parent / "fixtures"
MB = 1024 * 1024


@pytest.fixture
def session_id(client):
    return client.post("/sessions", json={"instrument": "violin"}).json()["session_id"]


def upload(client, session_id, name, data):
    return client.post(f"/sessions/{session_id}/score/file", files={"file": (name, data)})


def use_builtin(client, session_id, piece_id="ode_to_joy"):
    return client.post(f"/sessions/{session_id}/score/file", json={"builtin": piece_id})


def score_json(client, session_id):
    return client.get(f"/sessions/{session_id}/score", params={"format": "json"}).json()


def assert_error(response, status, code):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error"} and body["error"]["code"] == code and body["error"]["message"]
    return body["error"]["message"]


def status_of(client, session_id):
    return client.get(f"/sessions/{session_id}").json()["score_status"]


def test_builtin_then_confirm_then_read_json(client, session_id):
    scanned = use_builtin(client, session_id)
    assert scanned.status_code == 200
    assert scanned.json() == {"score_status": "scanned", "bars": 16, "doubtful_bars": [], "double_checked": False, "warnings": []}
    assert status_of(client, session_id) == "scanned"

    confirmed = client.post(f"/sessions/{session_id}/score/confirm", json={})
    assert confirmed.json() == {"score_status": "confirmed", "bars": 16, "tempo_bpm": 96.0, "time_signature": [4, 4]}
    assert status_of(client, session_id) == "confirmed"

    score = score_json(client, session_id)
    assert len(score["bars"]) == 16 and score["bars"][0]["notes"][0]["name"] == "E4"


def test_get_score_returns_musicxml_by_default(client, session_id):
    use_builtin(client, session_id, "twinkle_trumpet")
    response = client.get(f"/sessions/{session_id}/score")
    assert response.headers["content-type"].startswith("application/vnd.recordare.musicxml+xml")
    assert "<score-partwise" in response.text and "<chromatic>-2</chromatic>" in response.text


def test_get_builtins_lists_and_filters(client):
    assert len(client.get("/builtins").json()) == 4
    trumpet = client.get("/builtins", params={"instrument": "trumpet"}).json()
    assert [p["instrument"] for p in trumpet] == ["trumpet", "trumpet"]
    assert set(trumpet[0]) == {"piece_id", "title", "instrument", "bars"}


def test_musicxml_upload_is_saved_and_scanned(client, session_id, sessions_root):
    response = upload(client, session_id, "two.musicxml", (FIXTURES / "two_parts.musicxml").read_bytes())
    assert response.status_code == 200
    assert response.json()["warnings"] and response.json()["score_status"] == "scanned"
    folder = sessions_root / session_id
    assert (folder / "score.json").is_file() and (folder / "score.musicxml").is_file()


def test_chords_are_a_warning_not_an_error(client, session_id):
    response = upload(client, session_id, "chords.musicxml", (FIXTURES / "chords.musicxml").read_bytes())
    assert response.status_code == 200 and response.json()["warnings"]


def test_midi_upload_is_exported_to_musicxml(client, session_id, sessions_root):
    assert upload(client, session_id, "tune.mid", (FIXTURES / "off_grid.mid").read_bytes()).status_code == 200
    assert (sessions_root / session_id / "score_source.mid").is_file()
    assert "<score-partwise" in client.get(f"/sessions/{session_id}/score").text


def test_new_upload_replaces_previous_result(client, session_id, sessions_root):
    use_builtin(client, session_id, "ode_to_joy")
    assert upload(client, session_id, "tune.mid", (FIXTURES / "off_grid.mid").read_bytes()).status_code == 200
    again = use_builtin(client, session_id, "twinkle")
    assert again.json()["bars"] == 12
    assert not list((sessions_root / session_id).glob("score_source.*"))
    assert len(score_json(client, session_id)["bars"]) == 12


def test_txt_upload_is_415_and_names_allowed_types(client, session_id):
    message = assert_error(upload(client, session_id, "notes.txt", b"hello"), 415, "unsupported_type")
    assert ".musicxml" in message and ".mid" in message


def test_six_mb_musicxml_is_413(client, session_id):
    message = assert_error(upload(client, session_id, "big.musicxml", b"x" * (6 * MB)), 413, "file_too_large")
    assert "5 MB" in message


def test_broken_xml_is_422_and_saves_nothing(client, session_id, sessions_root):
    response = upload(client, session_id, "broken.musicxml", (FIXTURES / "broken.musicxml").read_bytes())
    assert assert_error(response, 422, "bad_score_file") == "This file couldn't be read as sheet music."
    assert not (sessions_root / session_id / "score.json").exists()
    assert status_of(client, session_id) == "none"


def test_file_without_notes_is_422(client, session_id):
    response = upload(client, session_id, "empty.musicxml", (FIXTURES / "no_notes.musicxml").read_bytes())
    assert_error(response, 422, "bad_score_file")


def test_bad_upload_keeps_the_previous_scan(client, session_id):
    use_builtin(client, session_id)
    upload(client, session_id, "broken.musicxml", (FIXTURES / "broken.musicxml").read_bytes())
    assert status_of(client, session_id) == "scanned"
    assert len(score_json(client, session_id)["bars"]) == 16


def test_unknown_builtin_is_404(client, session_id):
    assert_error(use_builtin(client, session_id, "nope"), 404, "builtin_not_found")


@pytest.mark.parametrize(
    "kwargs",
    [{"json": {}}, {"json": {"builtin": 5}}, {"content": b"not json"}, {"files": {"other": ("a.xml", b"x")}}],
)
def test_malformed_requests_are_422(client, session_id, kwargs):
    assert_error(client.post(f"/sessions/{session_id}/score/file", **kwargs), 422, "bad_request")


def test_unknown_session_is_404_everywhere(client):
    for response in (
        client.post("/sessions/nope/score/file", json={"builtin": "twinkle"}),
        client.post("/sessions/nope/score/confirm", json={}),
        client.get("/sessions/nope/score"),
    ):
        assert_error(response, 404, "session_not_found")


def test_confirm_before_any_score_is_409(client, session_id):
    assert_error(client.post(f"/sessions/{session_id}/score/confirm", json={}), 409, "wrong_state")


def test_get_score_before_any_score_is_409(client, session_id):
    assert_error(client.get(f"/sessions/{session_id}/score"), 409, "wrong_state")


def test_upload_after_confirm_is_409_and_score_is_unchanged(client, session_id):
    use_builtin(client, session_id)
    client.post(f"/sessions/{session_id}/score/confirm", json={})
    assert_error(use_builtin(client, session_id, "twinkle"), 409, "wrong_state")
    assert_error(client.post(f"/sessions/{session_id}/score/confirm", json={}), 409, "wrong_state")
    assert len(score_json(client, session_id)["bars"]) == 16


def test_upload_while_scanning_is_409(client, session_id):
    store.update(session_id, "score_status", "scanning")
    assert_error(use_builtin(client, session_id), 409, "wrong_state")


def test_bad_format_is_422(client, session_id):
    use_builtin(client, session_id)
    assert_error(client.get(f"/sessions/{session_id}/score", params={"format": "pdf"}), 422, "bad_request")


def test_unwritable_session_folder_is_500_storage_error(client, session_id, monkeypatch, caplog):
    def fail(self, folder):
        raise OSError("disk full")

    monkeypatch.setattr(Score, "save", fail)
    with caplog.at_level(logging.ERROR):
        message = assert_error(use_builtin(client, session_id), 500, "storage_error")
    assert message == "The app couldn't save your work. Tell the team."
    assert session_id in caplog.text
    assert status_of(client, session_id) == "none"
