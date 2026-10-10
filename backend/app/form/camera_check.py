"""Camera check: is the learner in frame well enough to track? Used by the camera guide before recording."""
import threading

import cv2
import numpy as np

from . import config
from .tracker import Tracker, downscale

# Pose landmark indices of the points the rules need, with the plain name shown to the learner.
NEEDED_POINTS = [
    ("nose", 0), ("left ear", 7), ("right ear", 8),
    ("left shoulder", 11), ("right shoulder", 12),
    ("left elbow", 13), ("right elbow", 14),
    ("left wrist", 15), ("right wrist", 16),
]
HIP_POINTS = (23, 24)  # reported together as 'hips': they only serve the slouching check
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12

_trackers: dict[bool, Tracker] = {}  # one loaded tracker per with_hands, kept so no call reloads the models
_lock = threading.Lock()  # a MediaPipe landmarker handles one image at a time


def _loaded_tracker(with_hands: bool) -> Tracker:
    """The kept tracker, loaded on first use. A failed load raises FormUnavailable and is retried next call."""
    if with_hands not in _trackers:
        _trackers[with_hands] = Tracker(with_hands, video=False)
    return _trackers[with_hands]


def _seen(pose: list[list[float]] | None, index: int) -> bool:
    """Visible enough and inside the picture: MediaPipe guesses points past the edge with high visibility."""
    if pose is None:
        return False
    x, y, visibility = pose[index]
    return visibility >= config.VISIBILITY_MIN and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def _missing_points(frame: dict, with_hands: bool) -> list[str]:
    pose = frame["pose"]
    missing = [name for name, index in NEEDED_POINTS if not _seen(pose, index)]
    if not all(_seen(pose, index) for index in HIP_POINTS):
        missing.append("hips")
    if with_hands and frame["left_hand"] is None:
        missing.append("left hand")
    return missing


def _too_small(pose: list[list[float]] | None) -> bool:
    """True when both shoulders are seen but closer together than the minimum share of the image width."""
    if not (_seen(pose, LEFT_SHOULDER) and _seen(pose, RIGHT_SHOULDER)):
        return False
    return abs(pose[LEFT_SHOULDER][0] - pose[RIGHT_SHOULDER][0]) < config.CAMERA_MIN_SHOULDER_WIDTH


def check_camera_frame(bgr: np.ndarray, instrument: str) -> dict:
    """{ok, missing, too_small, too_dark} for one camera frame. Raises FormUnavailable if MediaPipe can't load."""
    with_hands = instrument == "violin"
    with _lock:
        frame = _loaded_tracker(with_hands).track(downscale(bgr))
    missing = _missing_points(frame, with_hands)
    too_small = _too_small(frame["pose"])
    too_dark = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()) < config.CAMERA_MIN_BRIGHTNESS
    return {"ok": not (missing or too_small or too_dark), "missing": missing, "too_small": too_small, "too_dark": too_dark}
