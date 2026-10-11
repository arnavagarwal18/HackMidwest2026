"""The app's bell-angle proxy equals the one the good-set statistics were taken with (scripts/posture_stats_measures.py)."""
import sys
from pathlib import Path

import pytest
from form_frames import timeline
from form_side_frames import frames_of, side_frame

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from app.form.bell_measures import BELL_ANGLE, BELL_HEIGHT, FRONT_BELL_SPECS, side_bell_specs  # noqa: E402
from app.form.measures import frame_measures  # noqa: E402
from posture_stats_measures import BELL_PROXY, measure_specs  # noqa: E402


@pytest.mark.parametrize("bell_height", [-0.8, 0.0, 0.7, 2.4])
def test_front_bell_height_equals_the_statistics_proxy(bell_height):
    frame = timeline((0.1, {"bell_height": bell_height}))[0]
    ours = frame_measures(frame, specs=FRONT_BELL_SPECS)[BELL_HEIGHT].value
    theirs = frame_measures(frame, specs=measure_specs("front", "left"))[BELL_PROXY].value
    assert ours == pytest.approx(theirs) == pytest.approx(bell_height)


@pytest.mark.parametrize("near", ["left", "right"])
@pytest.mark.parametrize("bell_angle", [-110.0, -40.0, 5.0])
def test_side_bell_angle_equals_the_statistics_proxy(near, bell_angle):
    frame = frames_of(side_frame, (0.1, {"near": near, "bell_angle": bell_angle}))[0]
    ours = frame_measures(frame, specs=side_bell_specs(near))[BELL_ANGLE].value
    theirs = frame_measures(frame, specs=measure_specs("side", near))[BELL_PROXY].value
    assert ours == pytest.approx(theirs) == pytest.approx(bell_angle)


def test_side_bell_angle_reads_the_same_facing_left_as_facing_right():
    frame = frames_of(side_frame, (0.1, {"bell_angle": -40.0}))[0]
    mirrored = {**frame, "pose": [[1.0 - x, y, v] for x, y, v in frame["pose"]]}
    left = frame_measures(frame, specs=side_bell_specs("left"))[BELL_ANGLE].value
    right = frame_measures(mirrored, specs=side_bell_specs("left"))[BELL_ANGLE].value
    assert right == pytest.approx(left)


def test_side_bell_angle_is_missing_when_the_nose_is_straight_above_the_ear():
    frame = frames_of(side_frame, (0.1, {}))[0]
    frame["pose"][0][0] = frame["pose"][7][0]
    assert frame_measures(frame, specs=side_bell_specs("left"))[BELL_ANGLE].value is None
