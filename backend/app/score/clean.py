"""Photo clean-up before homr reads it: upright, grayscale, 2000 px, staff lines level.

Steps (LLD-1): apply the EXIF orientation and drop the EXIF data, convert to grayscale, scale so the longer
side is 2000 px, straighten by the staff lines' median angle (only if it is 0.5 to 10 degrees), save a PNG.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.score.exceptions import ScanError

logger = logging.getLogger(__name__)

CLEANED_FILENAME = "cleaned.png"
TARGET_LONG_SIDE = 2000
MIN_ROTATION_DEGREES = 0.5
MAX_ROTATION_DEGREES = 10.0
MAX_STAFF_ANGLE_DEGREES = 45.0  # steeper lines are stems or barlines, not staff lines
MIN_LINE_LENGTH_FRACTION = 0.25  # of the image width
WHITE = 255


def clean_photo(source: Path, target: Path) -> Path:
    """Write the cleaned photo to `target` (a PNG); raises ScanError('scan_failed') if the image can't be read."""
    gray = _load_upright_gray(source)
    gray = _scale_to_long_side(gray, TARGET_LONG_SIDE)
    angle = estimate_skew_degrees(gray)
    if angle is not None and MIN_ROTATION_DEGREES <= abs(angle) <= MAX_ROTATION_DEGREES:
        gray = _rotate(gray, angle)
    elif angle is not None:
        logger.info("Leaving %s unrotated: staff angle %.1f degrees is outside %.1f to %.1f", source.name, angle, MIN_ROTATION_DEGREES, MAX_ROTATION_DEGREES)
    if not cv2.imwrite(str(target), gray):
        raise ScanError("scan_failed", f"Could not write the cleaned photo to {target}")
    return target


def estimate_skew_degrees(gray: np.ndarray) -> float | None:
    """Median angle (degrees, positive = sloping down to the right) of long near-horizontal lines, or None if there are none."""
    height, width = gray.shape
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=math.pi / 720,
        threshold=100,
        minLineLength=int(width * MIN_LINE_LENGTH_FRACTION),
        maxLineGap=20,
    )
    if lines is None:
        return None
    angles = [math.degrees(math.atan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in lines[:, 0]]
    staff_angles = [angle for angle in angles if abs(angle) <= MAX_STAFF_ANGLE_DEGREES]
    return float(np.median(staff_angles)) if staff_angles else None


def _load_upright_gray(source: Path) -> np.ndarray:
    try:
        with Image.open(source) as opened:
            upright = ImageOps.exif_transpose(opened)  # returns a copy without the orientation tag
            gray = upright.convert("L")
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        logger.exception("Could not read the photo %s", source)
        raise ScanError("scan_failed", f"Could not read the photo {source.name}: {exc}") from exc
    return np.asarray(gray)  # a plain array carries no EXIF into the saved PNG


def _scale_to_long_side(gray: np.ndarray, long_side: int) -> np.ndarray:
    height, width = gray.shape
    factor = long_side / max(height, width)
    if factor == 1:
        return gray
    size = (max(1, round(width * factor)), max(1, round(height * factor)))
    return cv2.resize(gray, size, interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC)


def _rotate(gray: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate counter-clockwise by `degrees` on a canvas big enough to keep every corner, filling with white."""
    height, width = gray.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width = int(round(height * sin + width * cos))
    new_height = int(round(height * cos + width * sin))
    matrix[0, 2] += new_width / 2 - width / 2
    matrix[1, 2] += new_height / 2 - height / 2
    return cv2.warpAffine(gray, matrix, (new_width, new_height), flags=cv2.INTER_LINEAR, borderValue=WHITE)
