"""Step 3c: the bell-angle proxy, where the hands are relative to the mouth, as a stand-in for where a trumpet bell points.

The trumpet runs from the mouthpiece at the mouth through the hands to the bell. Mouth = midpoint of pose landmarks 9 and 10,
hands = midpoint of the wrists (landmarks 15 and 16). Image-space proxies, not true bell angles; the two views read opposite ways.
(backend/scripts/posture_stats_measures.py holds the same definitions the good-set statistics were taken with; a test keeps them equal.)
"""
import math

from .measures import (LEFT_SHOULDER, LEFT_WRIST, NOSE, RIGHT_SHOULDER, MeasureSpec, _midpoint, _shoulder_width)
from .side_measures import NEAR_POINTS

MOUTH_LEFT, MOUTH_RIGHT, RIGHT_WRIST = 9, 10, 16

BELL_HEIGHT = "bell_height"  # front view: (wrist midpoint y - mouth y) / shoulder width, positive = wrists BELOW the mouth
BELL_ANGLE = "bell_angle"  # side view: degrees above horizontal from the mouth to the wrist midpoint, positive = wrists higher

_MOUTH_AND_WRISTS = (MOUTH_LEFT, MOUTH_RIGHT, LEFT_WRIST, RIGHT_WRIST)


def _bell_height(pose, hands) -> float | None:
    width = _shoulder_width(pose)
    if width is None:
        return None
    return (_midpoint(pose, LEFT_WRIST, RIGHT_WRIST)[1] - _midpoint(pose, MOUTH_LEFT, MOUTH_RIGHT)[1]) / width


def _bell_angle(ear: int):
    def measure(pose, hands) -> float | None:
        facing = pose[NOSE][0] - pose[ear][0]  # the way the nose points from the near ear, so both facing directions read the same
        if facing == 0:
            return None
        mouth, wrists = _midpoint(pose, MOUTH_LEFT, MOUTH_RIGHT), _midpoint(pose, LEFT_WRIST, RIGHT_WRIST)
        return math.degrees(math.atan2(mouth[1] - wrists[1], math.copysign(1.0, facing) * (wrists[0] - mouth[0])))

    return measure


FRONT_BELL_SPECS = {BELL_HEIGHT: MeasureSpec((LEFT_SHOULDER, RIGHT_SHOULDER) + _MOUTH_AND_WRISTS, _bell_height)}


def side_bell_specs(side: str) -> dict[str, MeasureSpec]:
    """The side-view bell measure for the near `side` ('left' or 'right')."""
    ear = NEAR_POINTS[side][0]
    return {BELL_ANGLE: MeasureSpec((NOSE, ear) + _MOUTH_AND_WRISTS, _bell_angle(ear))}
