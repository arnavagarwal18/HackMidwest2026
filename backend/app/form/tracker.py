"""MediaPipe Pose (and Hands) behind one small class, plus a one-image helper for the camera check."""
import logging

import cv2
import numpy as np

from . import config
from .errors import FormUnavailable
from .hand_sides import assign_hands

logger = logging.getLogger("app.form.tracker")

_unavailable_logged = False


def _log_unavailable_once(reason: Exception) -> None:
    global _unavailable_logged
    if not _unavailable_logged:
        _unavailable_logged = True
        logger.error("Form analysis is unavailable: %s", reason, exc_info=reason)


def downscale(bgr: np.ndarray) -> np.ndarray:
    """The frame scaled down to at most MAX_WIDTH pixels wide (smaller frames are left alone)."""
    height, width = bgr.shape[:2]
    if width <= config.MAX_WIDTH:
        return bgr
    return cv2.resize(bgr, (config.MAX_WIDTH, round(height * config.MAX_WIDTH / width)), interpolation=cv2.INTER_AREA)


def _round(value: float) -> float:
    return round(float(value), config.COORDINATE_DECIMALS)


class Tracker:
    """Pose, and hands when asked, on one frame at a time. Use as a context manager; raises FormUnavailable if MediaPipe or a model can't load."""

    def __init__(self, with_hands: bool, video: bool):
        self._video = video
        self._pose = None
        self._hands = None
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import BaseOptions, vision

            self._mp = mp
            mode = vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE
            self._pose = vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(config.POSE_MODEL_PATH)), running_mode=mode))
            if with_hands:
                self._hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=str(config.HAND_MODEL_PATH)),
                    running_mode=mode, num_hands=config.HANDS_MAX))
        except Exception as exc:
            self.close()
            _log_unavailable_once(exc)
            raise FormUnavailable(f"{type(exc).__name__}: {exc}") from exc

    def __enter__(self) -> "Tracker":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        for landmarker in (self._pose, self._hands):
            if landmarker is not None:
                landmarker.close()
        self._pose = self._hands = None

    def _detect(self, landmarker, image, timestamp_ms: int):
        if self._video:
            return landmarker.detect_for_video(image, timestamp_ms)
        return landmarker.detect(image)

    def track(self, bgr: np.ndarray, timestamp_ms: int = 0) -> dict:
        """{pose, left_hand, right_hand} for one frame (already downscaled); None where nothing was found.

        In video mode timestamp_ms must grow from one call to the next.
        """
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        pose_result = self._detect(self._pose, image, timestamp_ms)
        pose = None
        if pose_result.pose_landmarks:
            landmarks = pose_result.pose_landmarks[0][:config.POSE_LANDMARK_COUNT]
            pose = [[_round(p.x), _round(p.y), _round(p.visibility)] for p in landmarks]
        hands = []
        if self._hands is not None:
            hand_result = self._detect(self._hands, image, timestamp_ms)
            hands = [[[_round(p.x), _round(p.y)] for p in hand] for hand in hand_result.hand_landmarks]
        left_hand, right_hand = assign_hands(pose, hands)
        return {"pose": pose, "left_hand": left_hand, "right_hand": right_hand}


def track_image(bgr: np.ndarray, with_hands: bool = False) -> dict:
    """Track one still image (any size; it is downscaled first). Same shape as one frame of the tracks file, without t."""
    with Tracker(with_hands, video=False) as tracker:
        return tracker.track(downscale(bgr))
