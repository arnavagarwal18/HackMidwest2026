import io

import numpy as np
import pytest
from PIL import Image

from app.score import clean
from app.score.exceptions import ScanError
from tests.photo_factory import encode, rotate_counter_clockwise, staff_image


def run_clean(tmp_path, image_bytes, suffix=".png"):
    source = tmp_path / f"photo{suffix}"
    source.write_bytes(image_bytes)
    target = clean.clean_photo(source, tmp_path / "cleaned.png")
    return Image.open(target)


def skew_of(cleaned):
    return clean.estimate_skew_degrees(np.asarray(cleaned))


def test_level_photo_is_scaled_to_2000_px_and_left_unrotated(tmp_path):
    cleaned = run_clean(tmp_path, encode(staff_image()))
    assert cleaned.mode == "L"
    assert cleaned.size == (2000, 875)
    assert abs(skew_of(cleaned)) < 0.5


@pytest.mark.parametrize("tilt", [5.0, -5.0, 8.0])
def test_tilted_photo_comes_out_level(tmp_path, tilt):
    tilted = rotate_counter_clockwise(staff_image(), tilt)
    assert abs(skew_of(tilted) + tilt) < 0.5  # the generated photo really is tilted
    cleaned = run_clean(tmp_path, encode(tilted))
    assert abs(skew_of(cleaned)) < 1.0
    assert max(cleaned.size) >= 2000  # the canvas grew to keep the corners


def test_photo_tilted_20_degrees_is_left_alone(tmp_path):
    tilted = rotate_counter_clockwise(staff_image(), 20.0)
    cleaned = run_clean(tmp_path, encode(tilted))
    assert max(cleaned.size) == 2000
    assert abs(skew_of(cleaned) + 20.0) < 1.0


def test_exif_orientation_is_applied_and_exif_dropped(tmp_path):
    upright = staff_image()
    stored_sideways = Image.fromarray(upright).rotate(90, expand=True)  # a phone stores it this way with Orientation 8
    exif = Image.Exif()
    exif[0x0112] = 8
    buffer = io.BytesIO()
    stored_sideways.save(buffer, format="JPEG", exif=exif.tobytes())
    assert Image.open(io.BytesIO(buffer.getvalue())).size[0] < 1000  # stored portrait

    cleaned = run_clean(tmp_path, buffer.getvalue(), suffix=".jpg")
    assert cleaned.size[0] > cleaned.size[1]
    assert abs(skew_of(cleaned)) < 1.0
    assert len(cleaned.getexif()) == 0


def test_unreadable_image_is_a_scan_failure(tmp_path):
    with pytest.raises(ScanError) as caught:
        run_clean(tmp_path, b"not an image")
    assert caught.value.code == "scan_failed"
