"""Step 2b: which way the camera faces the player (front or side), from the shoulder width against the shoulder-to-nose height."""
import logging
import math
from statistics import median

from . import config
from .measures import LEFT_SHOULDER, NOSE, RIGHT_SHOULDER, _midpoint, _scale_x

logger = logging.getLogger("app.form")

FRONT, SIDE = "front", "side"
LEFT, RIGHT = "left", "right"


def _view_ratio(pose) -> float | None:
    """Shoulder width over the vertical distance from the shoulder midpoint to the nose, in pixels; None if there is no height."""
    try:
        height = abs(pose[NOSE][1] - _midpoint(pose, LEFT_SHOULDER, RIGHT_SHOULDER)[1])
        width = math.dist(pose[LEFT_SHOULDER][:2], pose[RIGHT_SHOULDER][:2])
    except (IndexError, TypeError):
        return None
    return width / height if height > 0 else None


def detect_view(frames: list[dict], aspect: float = 1.0) -> tuple[str, float | None]:
    """(view, view_ratio): the median ratio over the tracked frames, 'side' when under VIEW_SIDE_MAX.

    With fewer than VIEW_MIN_FRAMES usable frames the view is 'front' and the ratio None. `aspect` is width / height of the video.
    """
    ratios = [r for r in (_view_ratio(_scale_x(f.get("pose"), aspect)) for f in frames if f.get("pose")) if r is not None]
    if len(ratios) < config.VIEW_MIN_FRAMES:
        logger.warning("camera view: only %d usable frames, assuming a front view", len(ratios))
        return FRONT, None
    ratio = median(ratios)
    return (SIDE if ratio < config.VIEW_SIDE_MAX else FRONT), round(ratio, config.COORDINATE_DECIMALS)


def near_side(frames: list[dict]) -> str:
    """The side of the body nearer the camera: the shoulder with the higher median visibility ('left' on a tie)."""
    visibility = {LEFT: [], RIGHT: []}
    for frame in frames:
        pose = frame.get("pose")
        if not pose:
            continue
        for side, index in ((LEFT, LEFT_SHOULDER), (RIGHT, RIGHT_SHOULDER)):
            if index < len(pose) and len(pose[index]) > 2:
                visibility[side].append(float(pose[index][2]))
    medians = {side: median(values) if values else 0.0 for side, values in visibility.items()}
    return RIGHT if medians[RIGHT] > medians[LEFT] else LEFT
