"""Synthetic sheet-music photos for tests: black staff lines and note heads on white."""
import io

import cv2
import numpy as np
from PIL import Image

STAFF_GAP = 14


def staff_image(width: int = 1600, height: int = 700) -> np.ndarray:
    """Grayscale image with three five-line staves and a few note heads."""
    image = np.full((height, width), 255, dtype=np.uint8)
    for top in (120, 320, 520):
        for line in range(5):
            y = top + line * STAFF_GAP
            cv2.line(image, (80, y), (width - 80, y), 0, 2)
        for x in range(200, width - 200, 150):
            cv2.ellipse(image, (x, top + STAFF_GAP * 2), (9, 7), -20, 0, 360, 0, -1)
    return image


def rotate_counter_clockwise(image: np.ndarray, degrees: float) -> np.ndarray:
    """Rotate on a bigger white canvas so nothing is cut off."""
    height, width = image.shape
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), degrees, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_width, new_height = int(height * sin + width * cos), int(height * cos + width * sin)
    matrix[0, 2] += new_width / 2 - width / 2
    matrix[1, 2] += new_height / 2 - height / 2
    return cv2.warpAffine(image, matrix, (new_width, new_height), borderValue=255)


def encode(image: np.ndarray, fmt: str = "PNG", **save_args) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(image).save(buffer, format=fmt, **save_args)
    return buffer.getvalue()
