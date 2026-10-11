"""The fixed trumpet limits and the two new rules (LLD-4 change 11), on synthetic frames that are bad (or good) from the first frame.

Because the whole take is held in one pose, the baseline (the first 2 s) absorbs it: only a fixed limit can flag it.
"""
import pytest
from form_frames import RELAXED, timeline
from form_side_frames import frames_of, side_frame

from app.form import config
from app.form.bell_measures import BELL_HEIGHT, FRONT_BELL_SPECS
from app.form.measures import frame_measures
from app.form.rules import analyse

HOLD_S = 3.0
# Held in a front view, the right elbow follows its gap (not the elbow angle), so a leaning torso does not move it
FRONT_HOLD = {"elbow_gap_right": RELAXED["elbow_gap_right"]}


def front_flags(instrument: str, overrides: dict) -> list[dict]:
    return analyse(timeline((HOLD_S, {**FRONT_HOLD, **overrides})), instrument, "t1")["flags"]


def side_flags(overrides: dict) -> list[dict]:
    return analyse(frames_of(side_frame, (HOLD_S, overrides)), "trumpet", "t1")["flags"]


def rules_of(flags: list[dict]) -> list[str]:
    return [flag["rule"] for flag in flags]


# (rule, overrides that break it, the limit, measure value of a good pose, direction)
FRONT_CASES = [
    ("trumpet_head_down", {"head_drop": 0.40}, config.TRUMPET_HEAD_DROP_MAX, {"head_drop": 0.25}, "high"),
    ("shoulders_raised", {"neck_ratio": 0.10}, config.TRUMPET_NECK_RATIO_MIN, {"neck_ratio": 0.20}, "low"),
    ("slouching", {"torso_lean": 25.0}, config.SLOUCHING_TORSO_LEAN_DEG, {"torso_lean": 10.0}, "high"),
    ("trumpet_elbows_wide", {"elbow_gap_left": 1.6}, config.TRUMPET_ELBOWS_WIDE_GAP, {"elbow_gap_left": 1.1}, "high"),
    ("trumpet_elbows_wide", {"elbow_gap_right": 1.6}, config.TRUMPET_ELBOWS_WIDE_GAP, {"elbow_gap_right": 1.1}, "high"),
    ("trumpet_bell_angle", {"bell_height": -0.8}, config.TRUMPET_BELL_HEIGHT_MIN, {"bell_height": -0.3}, "low"),
    ("trumpet_bell_angle", {"bell_height": 2.4}, config.TRUMPET_BELL_HEIGHT_MAX, {"bell_height": 1.7}, "high"),
]
SIDE_CASES = [
    ("trumpet_head_down", {"head_pitch": 50.0}, config.TRUMPET_HEAD_PITCH_MAX, {"head_pitch": 30.0}, "high"),
    ("shoulders_raised", {"neck_side": 0.025, "head_pitch": 0.0}, config.TRUMPET_NECK_SIDE_MIN, {"neck_side": 0.06}, "low"),
    ("slouching", {"torso_lean": 25.0}, config.SLOUCHING_TORSO_LEAN_DEG, {"torso_lean": 10.0}, "high"),
    ("trumpet_bell_angle", {"bell_angle": 5.0}, config.TRUMPET_BELL_ANGLE_MAX, {"bell_angle": -15.0}, "high"),
    ("trumpet_bell_angle", {"bell_angle": -110.0}, config.TRUMPET_BELL_ANGLE_MIN, {"bell_angle": -90.0}, "low"),
]


@pytest.mark.parametrize("rule, bad, limit, good, direction", FRONT_CASES, ids=[f"{c[0]}-{list(c[1])[0]}-{c[4]}" for c in FRONT_CASES])
def test_a_front_pose_bad_from_the_first_frame_is_flagged_at_the_fixed_limit(rule, bad, limit, good, direction):
    [flag] = front_flags("trumpet", bad)
    assert (flag["rule"], flag["direction"], flag["threshold"]) == (rule, direction, pytest.approx(limit))
    assert flag["start_s"] == 0.0 and 0 < flag["severity"] <= 1
    assert front_flags("trumpet", good) == []


@pytest.mark.parametrize("rule, bad, limit, good, direction", SIDE_CASES, ids=[f"{c[0]}-{list(c[1])[0]}-{c[4]}" for c in SIDE_CASES])
def test_a_side_pose_bad_from_the_first_frame_is_flagged_at_the_fixed_limit(rule, bad, limit, good, direction):
    [flag] = side_flags(bad)
    assert (flag["rule"], flag["direction"], flag["threshold"]) == (rule, direction, pytest.approx(limit))
    assert flag["start_s"] == 0.0 and 0 < flag["severity"] <= 1
    assert side_flags(good) == []


def test_the_baseline_rules_still_catch_drift_from_a_good_start():
    frames = timeline((2.0, {}), (2.0, {"head_drop": 0.25}))  # 0.25 is under the fixed 0.30 but 0.30 above the -0.05 baseline
    [flag] = analyse(frames, "trumpet", "t1")["flags"]
    assert flag["rule"] == "trumpet_head_down" and flag["threshold"] == pytest.approx(RELAXED["head_drop"] + config.TRUMPET_HEAD_DOWN_DROP)


def test_a_fixed_limit_and_the_baseline_rule_give_one_flag_not_two():
    frames = timeline((2.0, {}), (2.0, {"head_drop": 0.45}))  # past both the baseline threshold and the fixed limit
    assert rules_of(analyse(frames, "trumpet", "t1")["flags"]) == ["trumpet_head_down"]


@pytest.mark.parametrize("overrides", [{"head_drop": 0.40}, {"neck_ratio": 0.10}, {"elbow_gap_left": 1.6}, {"bell_height": 2.4}])
def test_the_fixed_limits_and_new_rules_are_for_the_trumpet_only(overrides):
    assert front_flags("violin", overrides) == []


def test_elbows_wide_is_not_judged_in_a_side_view():
    analysis = analyse(frames_of(side_frame, (HOLD_S, {})), "trumpet", "t1")
    assert {"rule": "trumpet_elbows_wide", "reason": "not_for_view"} in analysis["rules_skipped"]
    assert "trumpet_elbows_wide" not in rules_of(analysis["flags"])


def test_the_bell_rule_is_skipped_when_the_wrists_are_not_visible():
    frames = timeline((HOLD_S, {"bell_height": 2.4}))
    for frame in frames:
        frame["pose"][16][2] = 0.1
    analysis = analyse(frames, "trumpet", "t1")
    assert {"rule": "trumpet_bell_angle", "reason": "not_visible"} in analysis["rules_skipped"]
    assert analysis["flags"] == []


def test_bell_height_is_wrist_midpoint_below_the_mouth_in_shoulder_widths():
    frame = timeline((0.1, {"bell_height": 1.25}))[0]
    assert frame_measures(frame, specs=FRONT_BELL_SPECS)[BELL_HEIGHT].value == pytest.approx(1.25)


def _untracked_start(*segments: tuple[float, dict]) -> list[dict]:
    """Frames with no person in the first 2 s (so the baseline is the default), then the segments."""
    lead_in = [{"t": round(i * 0.1, 6), "pose": None, "left_hand": None, "right_hand": None} for i in range(20)]
    later = timeline(*segments)
    return lead_in + [{**frame, "t": round(frame["t"] + 2.0, 6)} for frame in later]


def test_a_defaulted_baseline_does_not_set_the_head_drop_threshold():
    # head_drop 0.12 is 0.17 above the default baseline of -0.05 but under the fixed limit: ordinary playing, not a flag
    analysis = analyse(_untracked_start((HOLD_S, {"head_drop": 0.12})), "trumpet", "t1")
    assert analysis["baseline"]["defaulted"] is True
    assert analysis["flags"] == []


def test_a_defaulted_baseline_still_flags_a_head_drop_past_the_fixed_limit():
    [flag] = analyse(_untracked_start((HOLD_S, {"head_drop": 0.40})), "trumpet", "t1")["flags"]
    assert flag["rule"] == "trumpet_head_down" and flag["threshold"] == pytest.approx(config.TRUMPET_HEAD_DROP_MAX)


def test_a_defaulted_baseline_does_not_set_the_neck_ratio_threshold():
    # the default neck ratio 0.55 would put the threshold at 0.33; 0.25 is above the fixed 0.15
    assert analyse(_untracked_start((HOLD_S, {"neck_ratio": 0.25})), "trumpet", "t1")["flags"] == []
