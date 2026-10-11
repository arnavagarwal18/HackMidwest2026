"""Step 5c: the MediaPipe Face Landmarker on the player's face in the frames where a note sounds."""
import logging
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import config
from .face_crop import Box, Window, crop_face, cut, face_box_window

logger = logging.getLogger("app.form.face")

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
    """The Face Landmarker (Tasks API, one face, blendshapes on) behind `detect(rgb) -> blendshape scores or None`.

    After each detect, `last_box` is the face's bounding box (a Box in the image given) or None when there was no face.
    """

    def __init__(self):
        self.last_box: Box | None = None
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self._landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(config.FACE_MODEL_PATH)),
            running_mode=vision.RunningMode.IMAGE, num_faces=1, output_face_blendshapes=True))

    def detect(self, rgb: np.ndarray) -> dict[str, float] | None:
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        result = self._landmarker.detect(image)
        self.last_box = None
        if not result.face_blendshapes:
            return None
        xs, ys = [p.x for p in result.face_landmarks[0]], [p.y for p in result.face_landmarks[0]]
        self.last_box = (min(xs), min(ys), max(xs), max(ys))
        return {shape.category_name: shape.score for shape in result.face_blendshapes[0]}

    def close(self) -> None:
        self._landmarker.close()


def _create_landmarker():
    return _MediaPipeFaceLandmarker()


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
        self._last_window: Window | None = None  # around the last face found in this take
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

    def _windows_to_try(self, bgr: np.ndarray, pose: list | None) -> list[Window]:
        """Where to look, in order: the pose crop, the window around the last face found in this take, the whole frame."""
        height, width = bgr.shape[:2]
        pose_crop = crop_face(bgr, pose, self._view)
        wanted = [pose_crop.window if pose_crop else None, self._last_window, (0, 0, width, height)]
        windows = []
        for window in wanted:
            if window is not None and window not in windows:
                windows.append(window)
        return windows

    def _detect_in(self, bgr: np.ndarray, window: Window) -> FaceReading | None:
        """Run the landmarker on one window; a face found there makes the next frame's first fallback the window around it."""
        if self._landmarker is None:
            self._landmarker = _create_landmarker()
        blendshapes = self._landmarker.detect(cv2.cvtColor(cut(bgr, window), cv2.COLOR_BGR2RGB))
        if blendshapes is None:
            return None
        box = getattr(self._landmarker, "last_box", None)
        height, width = bgr.shape[:2]
        self._last_window = (face_box_window(box, window, width, height) if box else None) or window
        return _reading(blendshapes)

    def _detect(self, bgr: np.ndarray, pose: list | None) -> FaceReading | None:
        for window in self._windows_to_try(bgr, pose):
            reading = self._detect_in(bgr, window)
            if reading is not None:
                return reading
        return None

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
