"""Camera view detection (step 2b) and the side-view measures and rules (steps 3b and 5b), on synthetic poses."""
import pytest
from form_side_frames import frames_of, ratio_frame, side_frame

from app.form import config
from app.form.rules import analyse
from app.form.view import detect_view, near_side

RELAXED_S = 2.0  # lead-in that sets the baseline
FLAG_S = 2.0


def side_take(*segments, near: str = "left") -> list[dict]:
    relaxed = (RELAXED_S, {"near": near})
    return frames_of(side_frame, relaxed, *[(seconds, {"near": near, **overrides}) for seconds, overrides in segments])


def rules_of(analysis: dict) -> list[str]:
    return [flag["rule"] for flag in analysis["flags"]]


def test_shoulders_twice_the_nose_height_is_a_front_view():
    view, ratio = detect_view(frames_of(ratio_frame, (1.0, {"ratio": 2.0})))
    assert (view, ratio) == ("front", pytest.approx(2.0, abs=1e-3))


def test_shoulders_at_four_tenths_of_the_nose_height_is_a_side_view():
    view, ratio = detect_view(frames_of(ratio_frame, (1.0, {"ratio": 0.4})))
    assert (view, ratio) == ("side", pytest.approx(0.4, abs=1e-3))


def test_the_ratio_is_the_median_over_the_frames():
    frames = frames_of(ratio_frame, (0.6, {"ratio": 0.4}), (0.4, {"ratio": 3.0}))
    assert detect_view(frames)[0] == "side"


def test_the_ratio_is_measured_in_pixels_not_normalised_units():
    frames = frames_of(ratio_frame, (1.0, {"ratio": 1.4}))
    assert detect_view(frames)[0] == "side"  # square pixels
    assert detect_view(frames, aspect=4 / 3)[0] == "front"  # a 4:3 frame stretches x: the shoulders are wider in pixels


def test_fewer_than_five_usable_frames_is_a_front_view_without_a_ratio():
    few = frames_of(ratio_frame, (config.VIEW_MIN_FRAMES * 0.1 - 0.1, {"ratio": 0.4}))
    assert detect_view(few) == ("front", None)
    untracked = [{"t": 0.0, "pose": None, "left_hand": None, "right_hand": None}] * 10
    assert detect_view(untracked) == ("front", None)


def test_frames_with_no_height_are_not_usable():
    flat = frames_of(ratio_frame, (1.0, {"ratio": 0.4, "nose_height": 0.0}))
    assert detect_view(flat) == ("front", None)


def test_the_near_side_is_the_shoulder_seen_more_clearly():
    assert near_side(side_take(near="left")) == "left"
    assert near_side(side_take(near="right")) == "right"


def test_analyse_reports_the_view_and_ratio():
    side = analyse(side_take(), "trumpet", "t1")
    assert side["view"] == "side" and 0 < side["view_ratio"] < config.VIEW_SIDE_MAX
    front = analyse(frames_of(ratio_frame, (3.0, {"ratio": 2.0})), "trumpet", "t1")
    assert front["view"] == "front" and front["view_ratio"] == pytest.approx(2.0, abs=1e-3)
    assert front["baseline"].get("head_pitch") is None and front["baseline"].get("neck_side") is None


def test_side_baseline_takes_the_medians_of_the_first_seconds():
    baseline = analyse(side_take(), "trumpet", "t1")["baseline"]
    assert baseline["head_pitch"] == pytest.approx(10.0, abs=0.01)
    assert baseline["neck_side"] == pytest.approx(0.12, abs=1e-6)
    assert baseline["defaulted"] is False


@pytest.mark.parametrize("near", ["left", "right"])
def test_nose_20_degrees_below_baseline_for_2_s_is_one_head_down_flag(near):
    analysis = analyse(side_take((FLAG_S, {"head_pitch": 30.0}), near=near), "trumpet", "t1")
    assert rules_of(analysis) == ["trumpet_head_down"]
    flag = analysis["flags"][0]
    assert (flag["unit"], flag["direction"]) == ("deg", "high")
    assert flag["threshold"] == pytest.approx(10.0 + config.SIDE_HEAD_PITCH_DELTA, abs=0.01)
    assert flag["value"] == pytest.approx(30.0, abs=0.01)
    assert flag["start_s"] == pytest.approx(RELAXED_S) and flag["end_s"] == pytest.approx(RELAXED_S + FLAG_S)
    assert 0 < flag["severity"] <= 1


def test_a_small_head_drop_is_not_flagged():
    assert rules_of(analyse(side_take((FLAG_S, {"head_pitch": 20.0})), "trumpet", "t1")) == []


def test_neck_side_at_0_6_of_the_baseline_for_2_s_flags_shoulders_raised():
    analysis = analyse(side_take((FLAG_S, {"neck_side": 0.12 * 0.6})), "trumpet", "t1")
    assert rules_of(analysis) == ["shoulders_raised"]
    flag = analysis["flags"][0]
    assert flag["threshold"] == pytest.approx(config.SIDE_NECK_RATIO * 0.12, abs=1e-6)
    assert 0 < flag["severity"] <= 1


def test_neck_side_at_0_8_of_the_baseline_is_not_flagged():
    assert rules_of(analyse(side_take((FLAG_S, {"neck_side": 0.12 * 0.8})), "trumpet", "t1")) == []


def test_torso_lean_over_15_degrees_flags_slouching():
    analysis = analyse(side_take((FLAG_S, {"torso_lean": 30.0})), "trumpet", "t1")
    assert rules_of(analysis) == ["slouching"]
    assert analysis["flags"][0]["value"] == pytest.approx(30.0, abs=0.01)


def test_elbows_pinned_is_skipped_for_the_view_and_never_flagged():
    analysis = analyse(side_take((FLAG_S, {"head_pitch": 30.0})), "trumpet", "t1")
    assert {"rule": "trumpet_elbows_pinned", "reason": "not_for_view"} in analysis["rules_skipped"]
    assert "trumpet_elbows_pinned" not in rules_of(analysis)


def test_front_view_lists_no_rule_as_not_for_view():
    analysis = analyse(frames_of(ratio_frame, (3.0, {"ratio": 2.0})), "trumpet", "t1")
    assert all(skip["reason"] != "not_for_view" for skip in analysis["rules_skipped"])


def test_too_few_baseline_frames_default_the_head_pitch_and_skip_shoulders_raised():
    few = frames_of(side_frame, (config.BASELINE_MIN_FRAMES * 0.1 - 0.1, {}))  # one short of BASELINE_MIN_FRAMES
    later = [{**f, "t": f["t"] + RELAXED_S} for f in frames_of(side_frame, (3.0, {"neck_side": 0.12 * 0.5}))]
    analysis = analyse(few + later, "trumpet", "t1")
    assert analysis["view"] == "side"
    assert analysis["baseline"]["head_pitch"] == 0.0 and analysis["baseline"]["neck_side"] is None
    assert analysis["baseline"]["defaulted"] is True
    assert {"rule": "shoulders_raised", "reason": "not_visible"} in analysis["rules_skipped"]
    assert "shoulders_raised" not in rules_of(analysis)
