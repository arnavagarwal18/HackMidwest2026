import json

from app.form import track
from app.takes.take_store import update_take
from tests.form_helpers import add_form_take


def url(session_id, take_id="t1"):
    return f"/sessions/{session_id}/takes/{take_id}/tracks"


def write_tracks(session_id, take_id="t1"):
    tracks = {"fps": 10.0, "width": 640, "height": 480,
              "frames": [{"t": 0.0, "pose": None, "left_hand": None, "right_hand": None}]}
    track.tracks_path(session_id, take_id).write_text(json.dumps(tracks))
    return tracks


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


def test_409_while_the_form_check_is_processing_then_200_with_the_frames(client):
    session_id, take_id = add_form_take(form_status="processing")
    early = client.get(url(session_id, take_id))
    assert (early.status_code, early.json()) == (409, {"error": {"code": "wrong_state", "message": "Form analysis not finished."}})
    tracks = write_tracks(session_id, take_id)
    update_take(session_id, take_id, form_status="done")
    done = client.get(url(session_id, take_id))
    assert (done.status_code, done.json()) == (200, tracks)


def test_the_tracks_are_gzipped_when_the_browser_accepts_it(client):
    session_id, take_id = add_form_take()
    tracks = write_tracks(session_id, take_id)
    zipped = client.get(url(session_id, take_id), headers={"Accept-Encoding": "gzip"})
    assert zipped.headers["content-encoding"] == "gzip"
    assert zipped.json() == tracks  # the test client unzips it
    plain = client.get(url(session_id, take_id), headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in plain.headers
    assert plain.json() == tracks


def test_404_no_tracks_for_a_mic_take(client):
    session_id, take_id = add_form_take(kind="mic", form_status="none")
    assert error_of(client.get(url(session_id, take_id))) == (404, "no_tracks")


def test_404_no_tracks_when_a_done_take_has_lost_its_file(client):
    session_id, take_id = add_form_take()
    assert error_of(client.get(url(session_id, take_id))) == (404, "no_tracks")


def test_404_for_an_unknown_session_or_take(client):
    session_id, _ = add_form_take()
    assert error_of(client.get(url("nosuchsession"))) == (404, "session_not_found")
    assert error_of(client.get(url(session_id, "t9"))) == (404, "take_not_found")
