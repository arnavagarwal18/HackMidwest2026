"""Step 5c: the MediaPipe Face Landmarker on the player's face in the frames where a note sounds."""
import logging
import math
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config

logger = logging.getLogger("app.form.face")

NOSE, LEFT_EAR, RIGHT_EAR, LEFT_SHOULDER, RIGHT_SHOULDER = 0, 7, 8, 11, 12  # pose landmark indices
SIDE_VIEW = "side"
CHEEK_PUFF, SMILE_LEFT, SMILE_RIGHT = "cheekPuff", "mouthSmileLeft", "mouthSmileRight"  # blendshape names

_unavailable = False  # set by the first failure of the model; nothing retries until the process restarts


@dataclass(frozen=True)
class FaceReading:
    cheek_puff: float
    smile: float


@dataclass
class FaceResult:
    """What the Face Landmarker saw: for each frame time inside a note, a FaceReading, or None when no face was found."""

    readings: dict[float, FaceReading | None] = field(default_factory=dict)
    unavailable: bool = False  # the model could not load or crashed, so there are no readings

    @property
    def face_quality(self) -> float | None:
        """Frames with a face / frames run; None when the face tracking did not run (unavailable, or no frame inside a note)."""
        if self.unavailable or not self.readings:
            return None
        return sum(reading is not None for reading in self.readings.values()) / len(self.readings)


class _MediaPipeFaceLandmarker:
    """The Face Landmarker (Tasks API, one face, blendshapes on) behind `detect(rgb) -> blendshape scores or None`."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self._landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(config.FACE_MODEL_PATH)),
            running_mode=vision.RunningMode.IMAGE, num_faces=1, output_face_blendshapes=True))

    def detect(self, rgb: np.ndarray) -> dict[str, float] | None:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect(image)
        if not result.face_blendshapes:
            return None
        return {shape.category_name: shape.score for shape in result.face_blendshapes[0]}

    def close(self) -> None:
        self._landmarker.close()


def _create_landmarker():
    return _MediaPipeFaceLandmarker()


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


def crop_face(bgr: np.ndarray, pose: list | None, view: str) -> np.ndarray | None:
    """The full-resolution frame cut to a square centred on the nose (at least FACE_CROP_MIN_PX, clipped to the frame).

    None when the pose has no usable nose, or no shoulders (front view) or ear (side view) to size the square by.
    """
    if pose is None or not _visible(pose[NOSE]):
        return None
    height, width = bgr.shape[:2]
    side = _crop_side_px(pose, width, height, view)
    if side is None:
        return None
    half = max(side, config.FACE_CROP_MIN_PX) / 2
    centre_x, centre_y = pose[NOSE][0] * width, pose[NOSE][1] * height
    left, right = max(0, round(centre_x - half)), min(width, round(centre_x + half))
    top, bottom = max(0, round(centre_y - half)), min(height, round(centre_y + half))
    if right <= left or bottom <= top:
        return None
    return bgr[top:bottom, left:right]


def _reading(blendshapes: dict[str, float] | None) -> FaceReading | None:
    if blendshapes is None:
        return None
    return FaceReading(cheek_puff=blendshapes.get(CHEEK_PUFF, 0.0),
                       smile=max(blendshapes.get(SMILE_LEFT, 0.0), blendshapes.get(SMILE_RIGHT, 0.0)))


def _log_unavailable_once(reason: Exception) -> None:
    global _unavailable
    if not _unavailable:
        _unavailable = True
        logger.error("Embouchure checks are unavailable until the engine restarts: %s", reason, exc_info=reason)


class FaceReader:
    """Reads the face in the frames the tracker hands it, only those inside a played note. Use as a context manager.

    `notes` are the take's transcribed notes ({onset_s, offset_s}, video seconds). Any failure of the model, on the first
    frame or later, marks the result unavailable and is logged once; it never raises.
    """

    def __init__(self, notes: list[dict], view: str | None):
        self._spans = [(note["onset_s"], note["offset_s"]) for note in notes]
        self._view = view or ""
        self._landmarker = None
        self.result = FaceResult(unavailable=_unavailable)

    def __enter__(self) -> "FaceReader":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def _in_note(self, seconds: float) -> bool:
        return any(onset <= seconds < offset for onset, offset in self._spans)

    def _detect(self, bgr: np.ndarray, pose: list | None) -> FaceReading | None:
        crop = crop_face(bgr, pose, self._view)
        if crop is None:
            return None
        if self._landmarker is None:
            self._landmarker = _create_landmarker()
        return _reading(self._landmarker.detect(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)))

    def read(self, bgr: np.ndarray, seconds: float, frame: dict) -> None:
        """Record the face in this full-resolution frame when `seconds` falls inside a note; `frame` is its tracked pose."""
        if self.result.unavailable or not self._in_note(seconds):
            return
        try:
            self.result.readings[seconds] = self._detect(bgr, frame["pose"])
        except Exception as exc:
            _log_unavailable_once(exc)
            self.result = FaceResult(unavailable=True)
            self.close()
