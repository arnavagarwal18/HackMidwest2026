"""Where to look for the face in a full-resolution frame: square windows from the pose, from a remembered face box, or the whole frame."""
import math
from typing import NamedTuple

import numpy as np

from . import config

NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER = 0, 7, 8, 11, 12  # pose landmark indices
SIDE_VIEW = "side"

Window = tuple[int, int, int, int]  # left, top, right, bottom in full-frame pixels
Box = tuple[float, float, float, float]  # left, top, right, bottom; fractions of the image it was found in (0 to 1)


class Crop(NamedTuple):
    image: np.ndarray
    window: Window


def _visible(point) -> bool:
    return point[2] >= config.VISIBILITY_MIN


def _crop_side_px(pose: list, width: int, height: int, view: str) -> float | None:
    """Side of the face crop in pixels (before the minimum), from the shoulders (front view) or the near ear (side view)."""
    def pixels(index: int) -> tuple[float, float]:
        return pose[index][0] * width, pose[index][1] * height

    if view == SIDE_VIEW:
        ears = [index for index in (LEFT_EAR, RIGHT_EAR) if _visible(pose[index])]
        if not ears:
            return None
        near_ear = max(ears, key=lambda index: pose[index][2])
        return config.FACE_CROP_EAR_RATIO * math.dist(pixels(near_ear), pixels(NOSE))
    if not (_visible(pose[LEFT_SHOULDER]) and _visible(pose[RIGHT_SHOULDER])):
        return None
    return config.FACE_CROP_SHOULDER_RATIO * math.dist(pixels(LEFT_SHOULDER), pixels(RIGHT_SHOULDER))


def square_window(centre_x: float, centre_y: float, side: float, width: int, height: int) -> Window | None:
    """A square of at least FACE_CROP_MIN_PX around the centre, clipped to the frame; None when nothing of it is inside."""
    half = max(side, config.FACE_CROP_MIN_PX) / 2
    left, right = max(0, round(centre_x - half)), min(width, round(centre_x + half))
    top, bottom = max(0, round(centre_y - half)), min(height, round(centre_y + half))
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def pose_window(pose: list | None, width: int, height: int, view: str) -> Window | None:
    """The window centred on the pose nose; None when the pose has no usable nose, or no shoulders (front view) or ear (side view)."""
    if pose is None or not _visible(pose[NOSE]):
        return None
    side = _crop_side_px(pose, width, height, view)
    if side is None:
        return None
    return square_window(pose[NOSE][0] * width, pose[NOSE][1] * height, side, width, height)


def face_box_window(box: Box, window: Window, width: int, height: int) -> Window | None:
    """The window to try next time: centred on a face `box` found inside `window`, FACE_BOX_MARGIN times the box's larger side."""
    left, top, right, bottom = window
    box_left, box_right = left + box[0] * (right - left), left + box[2] * (right - left)
    box_top, box_bottom = top + box[1] * (bottom - top), top + box[3] * (bottom - top)
    side = config.FACE_BOX_MARGIN * max(box_right - box_left, box_bottom - box_top)
    return square_window((box_left + box_right) / 2, (box_top + box_bottom) / 2, side, width, height)


def cut(bgr: np.ndarray, window: Window) -> np.ndarray:
    left, top, right, bottom = window
    return bgr[top:bottom, left:right]


def crop_face(bgr: np.ndarray, pose: list | None, view: str) -> Crop | None:
    """The full-resolution frame cut to the pose window (a square centred on the nose); None when there is no such window."""
    height, width = bgr.shape[:2]
    window = pose_window(pose, width, height, view)
    return None if window is None else Crop(cut(bgr, window), window)
