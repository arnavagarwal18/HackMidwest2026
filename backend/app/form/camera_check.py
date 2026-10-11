"""Camera check: is the learner in frame well enough to track? Used by the camera guide before recording.

In a side view only the nose and the body side nearer the camera are required: the far side is hidden behind it.
"""
import threading

import cv2
import numpy as np

from . import config
from .tracker import Tracker, downscale
from .view import FRONT, LEFT, RIGHT, SIDE, near_side, view_for_ratio, view_ratio_of

NOSE = 0
# Pose landmark indices of the points the rules need, with the plain name shown to the learner.
NEEDED_POINTS = [
    ("nose", NOSE), ("left ear", 7), ("right ear", 8),
    ("left shoulder", 11), ("right shoulder", 12),
    ("left elbow", 13), ("right elbow", 14),
    ("left wrist", 15), ("right wrist", 16),
]
HIP_POINTS = (23, 24)  # reported together as 'hips': they only serve the slouching check
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
SIDE_PARTS = {"ear": (7, 8), "shoulder": (11, 12), "elbow": (13, 14), "wrist": (15, 16), "hip": (23, 24)}  # (left, right) pose indices

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


def _near_point_indices(side: str) -> dict[str, int]:
    """Plain name -> pose index of the points the side view needs on the near `side`."""
    slot = 0 if side == LEFT else 1
    return {f"{side} {part}": indices[slot] for part, indices in SIDE_PARTS.items()}


def _missing_points(frame: dict, with_hands: bool, side: str | None) -> list[str]:
    """The needed points not seen: the front view's, or only the near `side`'s in a side view."""
    pose = frame["pose"]
    if side is None:
        missing = [name for name, index in NEEDED_POINTS if not _seen(pose, index)]
        if not all(_seen(pose, index) for index in HIP_POINTS):
            missing.append("hips")
    else:
        needed = {"nose": NOSE, **_near_point_indices(side)}  # head_pitch needs the nose, seen or not from the side
        missing = [name for name, index in needed.items() if not _seen(pose, index)]
    if with_hands and frame["left_hand"] is None:
        missing.append("left hand")
    return missing


def _too_small(pose: list[list[float]] | None, side: str | None) -> bool:
    """True when the body is smaller than the minimum share of the image.

    Front: both shoulders are seen but closer together than the minimum share of the image width. Side: the near
    shoulder and hip are seen but closer together than that share of the image height.
    """
    if side is None:
        if not (_seen(pose, LEFT_SHOULDER) and _seen(pose, RIGHT_SHOULDER)):
            return False
        return abs(pose[LEFT_SHOULDER][0] - pose[RIGHT_SHOULDER][0]) < config.CAMERA_MIN_SHOULDER_WIDTH
    indices = _near_point_indices(side)
    shoulder, hip = indices[f"{side} shoulder"], indices[f"{side} hip"]
    if not (_seen(pose, shoulder) and _seen(pose, hip)):
        return False
    return abs(pose[hip][1] - pose[shoulder][1]) < config.CAMERA_MIN_SHOULDER_WIDTH


def _view_and_side(frame: dict, requested: str | None, aspect: float) -> tuple[str, str | None]:
    """(view, near side): the learner's choice ('front', 'left' or 'right'), else detected from this one image."""
    if requested == FRONT:
        return FRONT, None
    if requested in (LEFT, RIGHT):
        return SIDE, requested
    if view_for_ratio(view_ratio_of(frame, aspect)) == SIDE:
        return SIDE, near_side([frame])
    return FRONT, None


def check_camera_frame(bgr: np.ndarray, instrument: str, view: str | None = None) -> dict:
    """{ok, missing, too_small, too_dark, view, near_side} for one camera frame.

    `view` is what the learner chose ('front', or 'left' / 'right' for the side facing the camera); None detects it.
    Raises FormUnavailable if MediaPipe can't load.
    """
    with_hands = instrument == "violin"
    small = downscale(bgr)
    with _lock:
        frame = _loaded_tracker(with_hands).track(small)
    detected_view, side = _view_and_side(frame, view, small.shape[1] / small.shape[0])
    missing = _missing_points(frame, with_hands, side)
    too_small = _too_small(frame["pose"], side)
    too_dark = float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()) < config.CAMERA_MIN_BRIGHTNESS
    return {"ok": not (missing or too_small or too_dark), "missing": missing, "too_small": too_small,
            "too_dark": too_dark, "view": detected_view, "near_side": side}
