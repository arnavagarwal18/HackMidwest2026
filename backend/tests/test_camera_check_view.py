"""POST /sessions/{id}/camera-check in the side view: the `view` field, view detection from one image, near-side points only.

The tracker is replaced by one that returns a synthetic side pose (the real photo shows a person facing the camera).
"""
import cv2
import numpy as np
import pytest
from form_side_frames import ratio_frame, side_frame

from app.form import camera_check
from tests.test_camera_check import PHOTO_BGR, check, error_of, jpeg, new_session

BRIGHT_IMAGE = jpeg(np.full((480, 640, 3), 128, np.uint8))
FAR_SIDE_POINTS = {"left": (8, 14, 16, 24), "right": (7, 13, 15, 23)}  # ear, elbow, wrist, hip of the side away from the camera


class FixedPoseTracker:
    """Stands in for the MediaPipe tracker: every image shows the same pose."""

    def __init__(self, frame: dict):
        self.frame = frame

    def track(self, bgr):
        return {key: self.frame[key] for key in ("pose", "left_hand", "right_hand")}


def show(monkeypatch, frame: dict) -> None:
    monkeypatch.setattr(camera_check, "_trackers", {False: FixedPoseTracker(frame), True: FixedPoseTracker(frame)})


def side_pose(near: str = "left") -> dict:
    """A player seen from the `near` side whose far-side ear, elbow, wrist and hip are not visible."""
    frame = side_frame(0.0, near)
    for index in FAR_SIDE_POINTS[near]:
        frame["pose"][index][2] = 0.0
    return frame


def post_view(client, session_id: str, view: str | None):
    data = {} if view is None else {"view": view}
    return client.post(f"/sessions/{session_id}/camera-check", files={"file": ("frame.jpg", BRIGHT_IMAGE, "image/jpeg")}, data=data)


def test_a_side_pose_with_the_far_side_hidden_is_ok_when_the_learner_says_left(client, monkeypatch):
    show(monkeypatch, side_pose("left"))
    body = post_view(client, new_session(client), "left").json()
    assert body == {"ok": True, "missing": [], "too_small": False, "too_dark": False, "view": "side", "near_side": "left"}


def test_a_right_side_pose_with_the_far_side_hidden_is_ok_when_the_learner_says_right(client, monkeypatch):
    show(monkeypatch, side_pose("right"))
    body = post_view(client, new_session(client), "right").json()
    assert (body["ok"], body["missing"], body["view"], body["near_side"]) == (True, [], "side", "right")


def test_without_a_view_field_a_side_pose_is_detected_as_side_with_its_near_side(client, monkeypatch):
    session_id = new_session(client)
    for near in ("left", "right"):
        show(monkeypatch, side_pose(near))
        body = post_view(client, session_id, None).json()
        assert (body["ok"], body["missing"], body["view"], body["near_side"]) == (True, [], "side", near)


def test_without_a_view_field_a_front_pose_stays_front(client, monkeypatch):
    show(monkeypatch, ratio_frame(0.0, 2.0))
    body = post_view(client, new_session(client), None).json()
    assert (body["view"], body["near_side"]) == ("front", None)


def test_the_learner_saying_front_wins_over_a_side_looking_pose(client, monkeypatch):
    show(monkeypatch, side_pose("left"))
    body = post_view(client, new_session(client), "front").json()
    assert (body["view"], body["near_side"], body["ok"]) == ("front", None, False)
    assert {"right ear", "right elbow", "right wrist", "hips"} <= set(body["missing"])


def test_the_far_side_is_never_listed_in_missing_in_a_side_view(client, monkeypatch):
    frame = side_pose("left")
    for index in range(len(frame["pose"])):
        if index not in (0, 7, 11, 13, 15, 23):  # leave only the nose and the near side's points
            frame["pose"][index][2] = 0.0
    show(monkeypatch, frame)
    assert post_view(client, new_session(client), "left").json()["missing"] == []


def test_a_hidden_near_point_is_listed_by_its_side_name(client, monkeypatch):
    frame = side_pose("left")
    frame["pose"][7][2] = 0.0
    frame["pose"][23][2] = 0.0
    show(monkeypatch, frame)
    body = post_view(client, new_session(client), "left").json()
    assert (body["ok"], body["missing"]) == (False, ["left ear", "left hip"])


def test_a_hidden_nose_is_listed_in_a_side_view(client, monkeypatch):
    frame = side_pose("left")
    frame["pose"][0][2] = 0.0
    show(monkeypatch, frame)
    body = post_view(client, new_session(client), "left").json()
    assert (body["ok"], body["missing"]) == (False, ["nose"])


def test_the_learner_picking_the_other_side_requires_that_sides_points(client, monkeypatch):
    show(monkeypatch, side_pose("left"))
    body = post_view(client, new_session(client), "right").json()
    assert (body["view"], body["near_side"], body["ok"]) == ("side", "right", False)
    assert set(body["missing"]) == {"right ear", "right shoulder", "right elbow", "right wrist", "right hip"}


def test_side_view_too_small_uses_the_near_shoulder_to_hip_height(client, monkeypatch):
    frame = side_pose("left")
    frame["pose"][23][1] = frame["pose"][11][1] + 0.1  # hip only a tenth of the image height below the shoulder
    show(monkeypatch, frame)
    body = post_view(client, new_session(client), "left").json()
    assert (body["too_small"], body["ok"], body["missing"]) == (True, False, [])


def test_side_view_with_the_near_hip_missing_is_not_also_too_small(client, monkeypatch):
    frame = side_pose("left")
    frame["pose"][23][2] = 0.0
    show(monkeypatch, frame)
    assert post_view(client, new_session(client), "left").json()["too_small"] is False


def test_a_violin_side_view_still_needs_the_left_hand(client, monkeypatch):
    frame = side_pose("left")
    frame["left_hand"] = None
    show(monkeypatch, frame)
    assert post_view(client, new_session(client, "violin"), "left").json()["missing"] == ["left hand"]


@pytest.mark.parametrize("bad", ["back", "LEFT", "both"])
def test_an_invalid_view_is_422_in_the_error_shape(client, bad):
    response = post_view(client, new_session(client), bad)
    assert error_of(response) == (422, "bad_request")


def test_an_image_with_no_person_is_front_with_everything_missing(client):
    black = jpeg(np.zeros((480, 640, 3), np.uint8))
    body = check(client, new_session(client), black).json()
    assert (body["view"], body["near_side"]) == ("front", None)


def test_the_real_photo_with_the_learner_saying_left_checks_only_the_left_points(client):
    _, encoded = cv2.imencode(".jpg", PHOTO_BGR)
    response = client.post(f"/sessions/{new_session(client)}/camera-check",
                           files={"file": ("frame.jpg", encoded.tobytes(), "image/jpeg")}, data={"view": "left"})
    body = response.json()
    assert (response.status_code, body["view"], body["near_side"], body["missing"]) == (200, "side", "left", [])
