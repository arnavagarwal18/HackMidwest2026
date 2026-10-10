"""POST /sessions/{id}/camera-check on the fixture photo and crops of it.

pose_person.jpg (1000x667) shows one person standing with arms out to the sides: Pose finds every needed point (hips
included) with high visibility, but the shoulders are only about 10% of the image wide, so the photo as it stands
is too_small. No hand is found in it, so the violin check lists 'left hand'. A centre crop of the same photo
(x from 25% to 75%) makes the person big enough and is the "good photo" of these tests.
"""
import time

import cv2
import numpy as np
import pytest

from app.form import camera_check, config
from app.form.errors import FormUnavailable
from tests.form_helpers import PHOTO

PHOTO_BGR = cv2.imread(str(PHOTO))
HEIGHT, WIDTH = PHOTO_BGR.shape[:2]
GOOD_PHOTO = PHOTO_BGR[:, WIDTH // 4: WIDTH * 3 // 4]
ABOVE_THE_ELBOWS = PHOTO_BGR[: int(HEIGHT * 0.45), WIDTH // 4: WIDTH * 3 // 4]  # the person's elbows are at 47% of the height


def jpeg(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return encoded.tobytes()


def check(client, session_id: str, data: bytes, content_type: str = "image/jpeg"):
    return client.post(f"/sessions/{session_id}/camera-check", files={"file": ("frame.jpg", data, content_type)})


def new_session(client, instrument: str = "trumpet") -> str:
    return client.post("/sessions", json={"instrument": instrument}).json()["session_id"]


def error_of(response):
    return response.status_code, response.json()["error"]["code"]


def test_a_good_photo_is_ok_for_the_trumpet(client):
    response = check(client, new_session(client), jpeg(GOOD_PHOTO))
    assert (response.status_code, response.json()) == (200, {"ok": True, "missing": [], "too_small": False, "too_dark": False})


def test_the_whole_fixture_photo_shows_every_point_but_is_too_small(client):
    body = check(client, new_session(client), PHOTO.read_bytes()).json()
    assert body == {"ok": False, "missing": [], "too_small": True, "too_dark": False}


def test_a_photo_cropped_above_the_elbows_lists_the_elbows_and_hips(client):
    body = check(client, new_session(client), jpeg(ABOVE_THE_ELBOWS)).json()
    assert body["ok"] is False
    assert {"left elbow", "right elbow", "hips"} <= set(body["missing"])


def test_a_violin_session_also_needs_the_left_hand(client):
    body = check(client, new_session(client, "violin"), PHOTO.read_bytes()).json()
    assert body["missing"] == ["left hand"]
    trumpet_body = check(client, new_session(client, "trumpet"), PHOTO.read_bytes()).json()
    assert "left hand" not in trumpet_body["missing"]


def test_an_all_black_image_is_too_dark_with_everything_missing(client):
    body = check(client, new_session(client), jpeg(np.zeros((480, 640, 3), np.uint8))).json()
    assert body["too_dark"] is True and body["too_small"] is False and body["ok"] is False
    assert {name for name, _ in camera_check.NEEDED_POINTS} | {"hips"} == set(body["missing"])


def test_a_dim_photo_is_too_dark(client):
    dim = (GOOD_PHOTO * (config.CAMERA_MIN_BRIGHTNESS / 2 / GOOD_PHOTO.mean())).astype(np.uint8)
    body = check(client, new_session(client), jpeg(dim)).json()
    assert body["too_dark"] is True and body["ok"] is False


def test_503_form_unavailable_when_mediapipe_cannot_load(client, monkeypatch):
    def cannot_load(*args, **kwargs):
        raise FormUnavailable("no mediapipe here")

    monkeypatch.setattr(camera_check, "_trackers", {})
    monkeypatch.setattr(camera_check, "Tracker", cannot_load)
    response = check(client, new_session(client), jpeg(GOOD_PHOTO))
    assert error_of(response) == (503, "form_unavailable")
    assert response.json()["error"]["message"] == FormUnavailable.message


def test_404_for_an_unknown_session(client):
    assert error_of(check(client, "nosuchsession", jpeg(GOOD_PHOTO))) == (404, "session_not_found")


def test_413_when_the_file_is_over_2_mb(client):
    too_big = jpeg(GOOD_PHOTO) + b"\0" * config.CAMERA_CHECK_MAX_BYTES
    assert error_of(check(client, new_session(client), too_big)) == (413, "file_too_large")


@pytest.mark.parametrize("data", [b"not an image at all", b""])
def test_415_when_the_file_is_not_a_decodable_image(client, data):
    assert error_of(check(client, new_session(client), data, "text/plain")) == (415, "unsupported_type")


def test_422_when_no_file_is_sent(client):
    response = client.post(f"/sessions/{new_session(client)}/camera-check")
    assert error_of(response) == (422, "bad_request")


def test_a_call_takes_under_a_second_once_the_tracker_is_warm(client):
    session_id, data = new_session(client), jpeg(GOOD_PHOTO)
    assert check(client, session_id, data).status_code == 200  # loads the models
    started = time.perf_counter()
    assert check(client, session_id, data).status_code == 200
    assert time.perf_counter() - started < 1.0


def test_the_tracker_is_loaded_once_and_reused(client, monkeypatch):
    loads = []
    real_tracker = camera_check.Tracker

    def counting_tracker(*args, **kwargs):
        loads.append(args)
        return real_tracker(*args, **kwargs)

    monkeypatch.setattr(camera_check, "_trackers", {})
    monkeypatch.setattr(camera_check, "Tracker", counting_tracker)
    session_id = new_session(client)
    for _ in range(3):
        assert check(client, session_id, jpeg(GOOD_PHOTO)).status_code == 200
    assert len(loads) == 1
