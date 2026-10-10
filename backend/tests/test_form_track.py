import json
from types import SimpleNamespace

import cv2
import pytest

from app import store
from app.form import config, track
from app.form.errors import FormUnavailable, VideoUnreadable
from app.form.hand_sides import assign_hands
from app.form.tracker import Tracker, track_image
from tests.form_helpers import PHOTO, add_form_take, make_photo_video

POSE_POINTS = 25
HAND_POINTS = 21


def pose_with_wrists(left, right):
    pose = [[0.5, 0.5, 1.0] for _ in range(POSE_POINTS)]
    pose[config.LEFT_WRIST], pose[config.RIGHT_WRIST] = [*left, 1.0], [*right, 1.0]
    return pose


def hand_at(x, y):
    return [[x + 0.001 * i, y] for i in range(HAND_POINTS)]


def test_a_hand_nearest_the_left_wrist_is_the_left_hand():
    pose = pose_with_wrists(left=(0.7, 0.4), right=(0.3, 0.4))
    hand = hand_at(0.68, 0.42)
    assert assign_hands(pose, [hand]) == (hand, None)


def test_a_hand_nearest_the_right_wrist_is_the_right_hand():
    pose = pose_with_wrists(left=(0.7, 0.4), right=(0.3, 0.4))
    hand = hand_at(0.31, 0.4)
    assert assign_hands(pose, [hand]) == (None, hand)


def test_two_hands_near_one_wrist_still_take_one_side_each():
    pose = pose_with_wrists(left=(0.7, 0.4), right=(0.3, 0.4))
    close, other = hand_at(0.69, 0.4), hand_at(0.72, 0.4)
    assert assign_hands(pose, [other, close]) == (close, other)


def test_hands_without_a_pose_are_not_assigned():
    assert assign_hands(None, [hand_at(0.5, 0.5)]) == (None, None)


def fake_landmarks(points):
    return [SimpleNamespace(x=p[0], y=p[1], visibility=p[2] if len(p) > 2 else 1.0) for p in points]


def test_tracker_ignores_the_handedness_label_of_mediapipe():
    """A hand near the pose's left wrist is left_hand, even though MediaPipe's own label here says 'Right'."""
    pose = pose_with_wrists(left=(0.7, 0.4), right=(0.3, 0.4))
    near_left = hand_at(0.69, 0.4)
    hand_result = SimpleNamespace(hand_landmarks=[fake_landmarks(near_left)],
                                  handedness=[[SimpleNamespace(category_name="Right")]])
    pose_result = SimpleNamespace(pose_landmarks=[fake_landmarks(pose)])
    with Tracker(with_hands=True, video=False) as tracker:
        tracker._detect = lambda landmarker, image, timestamp_ms: hand_result if landmarker is tracker._hands else pose_result
        frame = tracker.track(cv2.imread(str(PHOTO)))
    assert frame["left_hand"] == [[round(x, 4), round(y, 4)] for x, y in near_left]
    assert frame["right_hand"] is None


def test_video_gives_a_tracks_file_with_good_tracking_quality(client):
    session_id, take_id = add_form_take(instrument="violin")
    make_photo_video(store.session_dir(session_id) / "t1.mp4")
    result = track.track_take(session_id, take_id)
    assert result.tracking_quality > 0.8
    assert (result.frames_total, result.fps, result.warning) == (12, 10.0, None)
    saved = json.loads(track.tracks_path(session_id, take_id).read_text())
    assert (saved["fps"], len(saved["frames"])) == (10.0, 12)
    assert saved["width"] <= config.MAX_WIDTH
    first = saved["frames"][0]
    assert set(first) == {"t", "pose", "left_hand", "right_hand"}
    assert len(first["pose"]) == POSE_POINTS and len(first["pose"][0]) == 3
    assert saved["frames"][1]["t"] == pytest.approx(0.1)


def test_every_nth_frame_is_sampled_when_the_video_is_faster_than_the_sample_rate(tmp_path):
    video = make_photo_video(tmp_path / "fast.mp4", frames=40, fps=20)
    result = track.track_video(video, with_hands=False)
    assert (result.fps, result.frames_total) == (10.0, 20)
    assert result.frames[1]["t"] == pytest.approx(0.1)


def test_the_time_limit_keeps_the_frames_done_so_far_and_warns(tmp_path):
    video = make_photo_video(tmp_path / "slow.mp4", frames=30)
    ticks = iter(range(100))  # each clock() call is one second later
    result = track.track_video(video, with_hands=False, time_limit_s=3.5, clock=lambda: next(ticks))
    assert 0 < result.frames_total < 30
    assert result.warning == f"partial: first {round(result.frames_total / 10)} s checked"


def test_a_file_that_is_not_a_video_is_unreadable(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    with pytest.raises(VideoUnreadable) as caught:
        track.track_video(broken, with_hands=False)
    assert (caught.value.code, caught.value.message) == ("video_unreadable", "Could not read the video frames.")


def test_a_missing_video_is_unreadable(tmp_path):
    with pytest.raises(VideoUnreadable):
        track.track_video(tmp_path / "missing.mp4", with_hands=False)


def test_track_image_finds_the_person_in_a_photo():
    frame = track_image(cv2.imread(str(PHOTO)))
    assert len(frame["pose"]) == POSE_POINTS
    assert (frame["left_hand"], frame["right_hand"]) == (None, None)


def test_a_missing_model_is_form_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "POSE_MODEL_PATH", tmp_path / "missing.task")
    with pytest.raises(FormUnavailable) as caught:
        Tracker(with_hands=False, video=False)
    assert caught.value.code == "form_unavailable"
