"""Step 3b: posture measures for a side view, taken on the body side nearer the camera, and the side baseline."""
import logging
import math
from dataclasses import replace
from statistics import median

from . import config
from .measures import (LEFT_EAR, LEFT_HIP, LEFT_SHOULDER, NOSE, RIGHT_EAR, RIGHT_HIP, RIGHT_SHOULDER, UP, Baseline,
                       MeasureSpec, Reading, _angle_between, _vector, baseline_values)
from .view import LEFT, RIGHT

logger = logging.getLogger("app.form")

HEAD_PITCH = "head_pitch"  # degrees the nose is below the near ear, positive = nose lower
NECK_SIDE = "neck_side"  # near ear to near shoulder, vertically, as a share of the frame height (pixels / height)
SIDE_TORSO_LEAN = "side_torso_lean"  # degrees between near hip to near shoulder and vertical

NEAR_POINTS = {LEFT: (LEFT_EAR, LEFT_SHOULDER, LEFT_HIP), RIGHT: (RIGHT_EAR, RIGHT_SHOULDER, RIGHT_HIP)}
DEFAULT_HEAD_PITCH = 0.0  # used when there are too few baseline frames


def side_specs(side: str) -> dict[str, MeasureSpec]:
    """The side measures for the near `side` ('left' or 'right'), each needing its landmarks visible."""
    ear, shoulder, hip = NEAR_POINTS[side]

    def head_pitch(pose, hands) -> float | None:
        run, drop = abs(pose[NOSE][0] - pose[ear][0]), pose[NOSE][1] - pose[ear][1]
        return math.degrees(math.atan2(drop, run)) if run or drop else None

    def neck_side(pose, hands) -> float | None:
        return abs(pose[shoulder][1] - pose[ear][1])

    def torso_lean(pose, hands) -> float | None:
        return _angle_between(_vector(pose[hip], pose[shoulder]), UP)

    return {HEAD_PITCH: MeasureSpec((NOSE, ear), head_pitch),
            NECK_SIDE: MeasureSpec((shoulder, ear), neck_side),
            SIDE_TORSO_LEAN: MeasureSpec((shoulder, hip), torso_lean)}


def with_side_baseline(baseline: Baseline, frames: list[dict], readings: list[dict[str, Reading]]) -> Baseline:
    """The baseline plus the medians of head_pitch and neck_side over the first BASELINE_SECONDS.

    With too few frames head_pitch defaults to 0 (and the baseline counts as defaulted); neck_side has no baseline.
    """
    def median_or_none(name: str) -> float | None:
        values = baseline_values(frames, readings, name)
        if len(values) < config.BASELINE_MIN_FRAMES:
            logger.warning("baseline %s: only %d usable frames in the first %.1f s", name, len(values), config.BASELINE_SECONDS)
            return None
        return median(values)

    head_pitch = median_or_none(HEAD_PITCH)
    return replace(baseline, head_pitch=DEFAULT_HEAD_PITCH if head_pitch is None else head_pitch,
                   neck_side=median_or_none(NECK_SIDE), defaulted=head_pitch is None)
