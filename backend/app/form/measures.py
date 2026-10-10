"""Steps 3 and 4: per-frame posture measures from pose landmarks, and the player's own baseline."""
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean, median

from . import config

logger = logging.getLogger("app.form")

# MediaPipe pose landmark indices, named by the learner's own left / right
NOSE, LEFT_EAR, RIGHT_EAR = 0, 7, 8
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST = 15
LEFT_HIP, RIGHT_HIP = 23, 24
# MediaPipe hand landmark indices
HAND_WRIST, HAND_MIDDLE_KNUCKLE = 0, 9

DOWN = (0.0, 1.0)  # image y grows downward
UP = (0.0, -1.0)

ELBOW_ANGLE = "elbow_angle"
NECK_RATIO = "neck_ratio"
TORSO_LEAN = "torso_lean"
HEAD_DROP = "head_drop"
ELBOW_GAP_LEFT = "elbow_gap_left"
ELBOW_GAP_RIGHT = "elbow_gap_right"
WRIST_BEND = "wrist_bend"


@dataclass(frozen=True)
class Reading:
    """One measure in one frame. `value` is None when missing; `visibility` is the mean visibility of the pose landmarks it uses."""

    value: float | None
    visibility: float


@dataclass(frozen=True)
class Baseline:
    neck_ratio: float
    head_drop: float
    defaulted: bool

    def to_dict(self) -> dict:
        return {"neck_ratio": self.neck_ratio, "head_drop": self.head_drop, "defaulted": self.defaulted}


def _point(landmarks, index: int):
    try:
        return landmarks[index]
    except (IndexError, TypeError):
        return None


def _visibility(pose, indices: tuple[int, ...]) -> float:
    if not pose:
        return 0.0
    values = []
    for index in indices:
        point = _point(pose, index)
        values.append(float(point[2]) if point is not None and len(point) > 2 else 0.0)
    return mean(values)


def _all_visible(pose, indices: tuple[int, ...]) -> bool:
    if not pose:
        return False
    for index in indices:
        point = _point(pose, index)
        if point is None or len(point) < 3 or point[2] < config.VISIBILITY_MIN:
            return False
    return True


def _midpoint(pose, first: int, second: int) -> tuple[float, float]:
    return ((pose[first][0] + pose[second][0]) / 2, (pose[first][1] + pose[second][1]) / 2)


def _shoulder_width(pose) -> float | None:
    width = math.dist(pose[LEFT_SHOULDER][:2], pose[RIGHT_SHOULDER][:2])
    return width if width > 0 else None


def _angle_between(a: tuple[float, float], b: tuple[float, float]) -> float | None:
    """Angle in degrees between two vectors, or None if either has no length."""
    length = math.hypot(*a) * math.hypot(*b)
    if length == 0:
        return None
    cosine = (a[0] * b[0] + a[1] * b[1]) / length
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _vector(start, end) -> tuple[float, float]:
    return (end[0] - start[0], end[1] - start[1])


def _elbow_angle(pose, hands) -> float | None:
    return _angle_between(_vector(pose[RIGHT_SHOULDER], pose[RIGHT_ELBOW]), DOWN)


def _neck_ratio(pose, hands) -> float | None:
    width = _shoulder_width(pose)
    if width is None:
        return None
    return abs(_midpoint(pose, LEFT_SHOULDER, RIGHT_SHOULDER)[1] - _midpoint(pose, LEFT_EAR, RIGHT_EAR)[1]) / width


def _torso_lean(pose, hands) -> float | None:
    hips = _midpoint(pose, LEFT_HIP, RIGHT_HIP)
    shoulders = _midpoint(pose, LEFT_SHOULDER, RIGHT_SHOULDER)
    return _angle_between(_vector(hips, shoulders), UP)


def _head_drop(pose, hands) -> float | None:
    width = _shoulder_width(pose)
    if width is None:
        return None
    return (pose[NOSE][1] - _midpoint(pose, LEFT_EAR, RIGHT_EAR)[1]) / width


def _elbow_gap(elbow: int, hip: int):
    def measure(pose, hands) -> float | None:
        width = _shoulder_width(pose)
        if width is None:
            return None
        return abs(pose[elbow][0] - pose[hip][0]) / width

    return measure


def _wrist_bend(pose, hands) -> float | None:
    left_hand = hands["left_hand"]
    if not left_hand or len(left_hand) <= HAND_MIDDLE_KNUCKLE:
        return None
    forearm = _vector(pose[LEFT_ELBOW], pose[LEFT_WRIST])
    return _angle_between(forearm, _vector(left_hand[HAND_WRIST], left_hand[HAND_MIDDLE_KNUCKLE]))


@dataclass(frozen=True)
class MeasureSpec:
    landmarks: tuple[int, ...]  # pose landmarks that must be visible
    compute: Callable


_SHOULDERS = (LEFT_SHOULDER, RIGHT_SHOULDER)
MEASURE_SPECS = {
    ELBOW_ANGLE: MeasureSpec((RIGHT_SHOULDER, RIGHT_ELBOW), _elbow_angle),
    NECK_RATIO: MeasureSpec(_SHOULDERS + (LEFT_EAR, RIGHT_EAR), _neck_ratio),
    TORSO_LEAN: MeasureSpec(_SHOULDERS + (LEFT_HIP, RIGHT_HIP), _torso_lean),
    HEAD_DROP: MeasureSpec(_SHOULDERS + (NOSE, LEFT_EAR, RIGHT_EAR), _head_drop),
    ELBOW_GAP_LEFT: MeasureSpec(_SHOULDERS + (LEFT_ELBOW, LEFT_HIP), _elbow_gap(LEFT_ELBOW, LEFT_HIP)),
    ELBOW_GAP_RIGHT: MeasureSpec(_SHOULDERS + (RIGHT_ELBOW, RIGHT_HIP), _elbow_gap(RIGHT_ELBOW, RIGHT_HIP)),
    WRIST_BEND: MeasureSpec((LEFT_ELBOW, LEFT_WRIST), _wrist_bend),
}


def aspect_ratio(width: int | None, height: int | None) -> float:
    """Factor that turns normalised x into the same scale as normalised y; None for both means square pixels."""
    if width is None and height is None:
        return 1.0
    if not width or not height or width <= 0 or height <= 0:
        raise ValueError(f"video width and height must both be positive numbers, got width={width!r} height={height!r}")
    return width / height


def _scale_x(points, aspect: float):
    if not points or aspect == 1.0:
        return points
    return [[point[0] * aspect, *point[1:]] for point in points]


def frame_measures(frame: dict, aspect: float = 1.0) -> dict[str, Reading]:
    """Every measure for one tracks-file frame; a measure is missing (value None) unless all its landmarks are visible.

    `aspect` is width / height of the video: x is scaled by it so angles and distance ratios are not distorted.
    """
    pose = _scale_x(frame.get("pose"), aspect)
    hands = {"left_hand": _scale_x(frame.get("left_hand"), aspect), "right_hand": _scale_x(frame.get("right_hand"), aspect)}
    readings = {}
    for name, spec in MEASURE_SPECS.items():
        value = spec.compute(pose, hands) if _all_visible(pose, spec.landmarks) else None
        readings[name] = Reading(value, _visibility(pose, spec.landmarks))
    return readings


def compute_baseline(frames: list[dict], readings: list[dict[str, Reading]]) -> Baseline:
    """The neutral neck_ratio and head_drop: medians over the first BASELINE_SECONDS, or the defaults when too few frames have them."""

    def neutral(name: str, default: float) -> tuple[float, bool]:
        values = [r[name].value for f, r in zip(frames, readings)
                  if f["t"] < config.BASELINE_SECONDS and r[name].value is not None]
        if len(values) < config.BASELINE_MIN_FRAMES:
            logger.warning("baseline %s: only %d usable frames in the first %.1f s, using default %s",
                           name, len(values), config.BASELINE_SECONDS, default)
            return default, True
        return median(values), False

    neck_ratio, neck_defaulted = neutral(NECK_RATIO, config.DEFAULT_NECK_RATIO)
    head_drop, head_defaulted = neutral(HEAD_DROP, config.DEFAULT_HEAD_DROP)
    return Baseline(neck_ratio, head_drop, neck_defaulted or head_defaulted)
