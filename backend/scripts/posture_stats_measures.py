"""The pure maths of posture_stats.py: which measures to take per camera view, the bell-angle proxy, and percentiles.

Bell-angle proxy (`bell_proxy`): where the player's hands are relative to the mouth, as a stand-in for where the bell points
(the trumpet runs from the mouthpiece at the mouth through the hands to the bell). Mouth = midpoint of pose landmarks 9 and 10,
hands = midpoint of the wrists (landmarks 15 and 16). x is scaled by the video's width / height first, as every form measure is.
  * side view: degrees above horizontal of the line from the mouth to the wrist midpoint, 0 = level, positive = wrists higher
    than the mouth, sign-corrected for the facing direction (the way the nose points from the near ear), so a player facing
    left and one facing right read the same. Needs the nose, the near ear, both mouth points and both wrists visible.
  * front view: (wrist midpoint y - mouth y) / shoulder width, positive = wrists BELOW the mouth. Needs both mouth points, both
    wrists and both shoulders visible. Note the opposite sign to the side view (both are image-space; neither is a true bell angle).
"""
import math

import numpy as np

from app.form.measures import (ELBOW_ANGLE, LEFT_SHOULDER, LEFT_WRIST, MEASURE_SPECS, NOSE, RIGHT_SHOULDER, WRIST_BEND,
                               MeasureSpec, _midpoint, _shoulder_width)
from app.form.side_measures import NEAR_POINTS, side_specs
from app.form.view import FRONT, SIDE

PERCENTILES = (1, 5, 50, 95, 99)
MOUTH_LEFT, MOUTH_RIGHT, RIGHT_WRIST = 9, 10, 16
BELL_PROXY = "bell_proxy"
VIOLIN_ONLY_MEASURES = (ELBOW_ANGLE, WRIST_BEND)


def _bell_front(pose, hands) -> float | None:
    width = _shoulder_width(pose)
    if width is None:
        return None
    return (_midpoint(pose, LEFT_WRIST, RIGHT_WRIST)[1] - _midpoint(pose, MOUTH_LEFT, MOUTH_RIGHT)[1]) / width


def _bell_side(ear: int):
    def measure(pose, hands) -> float | None:
        facing = np.sign(pose[NOSE][0] - pose[ear][0])
        if facing == 0:
            return None
        mouth, wrists = _midpoint(pose, MOUTH_LEFT, MOUTH_RIGHT), _midpoint(pose, LEFT_WRIST, RIGHT_WRIST)
        return math.degrees(math.atan2(mouth[1] - wrists[1], facing * (wrists[0] - mouth[0])))

    return measure


def measure_specs(view: str, near: str) -> dict[str, MeasureSpec]:
    """Every measure taken in `view` ('front' or 'side'; `near` is the side view's near body side).

    The front measures (head_drop, neck_ratio, torso_lean, elbow gaps) are taken in both views; the side view adds its own
    from app.form.side_measures. In a side view the front measures are scaled by a tiny shoulder width, so read them with care.
    """
    mouth_and_wrists = (MOUTH_LEFT, MOUTH_RIGHT, LEFT_WRIST, RIGHT_WRIST)
    specs = {name: spec for name, spec in MEASURE_SPECS.items() if name not in VIOLIN_ONLY_MEASURES}
    if view == SIDE:
        specs.update(side_specs(near))
        ear = NEAR_POINTS[near][0]
        specs[BELL_PROXY] = MeasureSpec((NOSE, ear) + mouth_and_wrists, _bell_side(ear))
    elif view == FRONT:
        specs[BELL_PROXY] = MeasureSpec((LEFT_SHOULDER, RIGHT_SHOULDER) + mouth_and_wrists, _bell_front)
    else:
        raise ValueError(f"view must be {FRONT!r} or {SIDE!r}, got {view!r}")
    return specs


def percentiles(values: list[float]) -> dict[int, float]:
    """The PERCENTILES of the values (linear interpolation); raises ValueError for an empty list."""
    if not values:
        raise ValueError("no values to take percentiles of")
    return dict(zip(PERCENTILES, (float(p) for p in np.percentile(values, PERCENTILES))))
