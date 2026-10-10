"""Form analysis steps 3 to 6 on synthetic landmark frames: measures, baseline, rules, episodes, skipped rules."""
import pytest
from form_frames import RELAXED, make_frame, timeline

from app.form import config
from app.form.measures import frame_measures
from app.form.rules import analyse

RELAXED_S = 2.0  # lead-in that sets the baseline

# rule name, instrument, overrides that break it, expected side
BREAKING = [
    ("violin_elbow_low", "violin", {"elbow_angle": 10.0}, "right"),
    ("violin_elbow_high", "violin", {"elbow_angle": 100.0}, "right"),
    ("violin_wrist_collapsed", "violin", {"wrist_bend": 50.0}, "left"),
    ("shoulders_raised", "violin", {"neck_ratio": 0.3}, "both"),
    ("slouching", "violin", {"torso_lean": 30.0}, None),
    ("trumpet_head_down", "trumpet", {"head_drop": 0.2}, None),
    ("trumpet_elbows_pinned", "trumpet", {"elbow_gap_left": 0.05}, "left"),
]
RULE_CASES = pytest.mark.parametrize("rule, instrument, bad, side", BREAKING, ids=[b[0] for b in BREAKING])


def run(instrument: str, *segments, take_id: str = "t1") -> dict:
    return analyse(timeline((RELAXED_S, {}), *segments), instrument, take_id)


def run_all(instrument: str, *segments, take_id: str = "t1") -> dict:
    """Like run, without the relaxed lead-in (for rules that depend on every frame)."""
    return analyse(timeline(*segments), instrument, take_id)


def test_measures_match_the_geometry():
    readings = frame_measures(make_frame(0.0, elbow_angle=30.0, neck_ratio=0.6, head_drop=0.1, torso_lean=12.0,
                                         elbow_gap_left=0.3, wrist_bend=25.0))
    values = {name: reading.value for name, reading in readings.items() if name != "elbow_gap_right"}
    assert values == pytest.approx({"elbow_angle": 30.0, "neck_ratio": 0.6, "head_drop": 0.1, "torso_lean": 12.0,
                                    "elbow_gap_left": 0.3, "wrist_bend": 25.0})
    assert frame_measures(make_frame(0.0, elbow_gap_right=0.2))["elbow_gap_right"].value == pytest.approx(0.2)


def test_measure_with_a_hidden_landmark_is_missing():
    frame = make_frame(0.0)
    frame["pose"][14][2] = 0.4  # right elbow below VISIBILITY_MIN
    frame["left_hand"] = None
    readings = frame_measures(frame)
    assert readings["elbow_angle"].value is None
    assert readings["wrist_bend"].value is None
    assert readings["neck_ratio"].value is not None


def test_frame_without_a_pose_has_every_measure_missing():
    readings = frame_measures({"t": 0.0, "pose": None, "left_hand": None, "right_hand": None})
    assert all(r.value is None and r.visibility == 0.0 for r in readings.values())


def test_elbow_at_ten_degrees_for_two_seconds_is_one_low_flag_with_half_severity():
    result = run("violin", (2.0, {"elbow_angle": 10.0}))
    [flag] = result["flags"]
    assert flag["rule"] == "violin_elbow_low"
    assert flag["start_s"] == pytest.approx(RELAXED_S, abs=0.1)
    assert flag["end_s"] == pytest.approx(RELAXED_S + 2.0, abs=0.1)
    assert flag["severity"] == pytest.approx(0.5)
    assert (flag["unit"], flag["direction"], flag["label"]) == ("deg", "low", "bow elbow too low")
    assert (flag["value"], flag["threshold"]) == pytest.approx((10.0, 20))


@RULE_CASES
def test_two_seconds_past_threshold_is_one_flag(rule, instrument, bad, side):
    result = run(instrument, (2.0, bad))
    [flag] = result["flags"]
    assert flag["rule"] == rule
    assert flag["side"] == side
    assert flag["start_s"] == pytest.approx(RELAXED_S, abs=0.1)
    assert flag["end_s"] == pytest.approx(RELAXED_S + 2.0, abs=0.1)
    assert flag["bars"] == [] and flag["linked"] == []
    assert flag["confidence"] == pytest.approx(1.0)
    assert result["rules_skipped"] == []


@RULE_CASES
def test_shorter_than_a_second_is_no_flag(rule, instrument, bad, side):
    assert run(instrument, (0.8, bad), (1.0, {}))["flags"] == []


@RULE_CASES
def test_two_runs_closer_than_half_a_second_merge(rule, instrument, bad, side):
    result = run(instrument, (1.0, bad), (0.3, {}), (1.0, bad))
    [flag] = result["flags"]
    assert flag["rule"] == rule
    assert flag["start_s"] == pytest.approx(RELAXED_S, abs=0.1)
    assert flag["end_s"] == pytest.approx(RELAXED_S + 2.3, abs=0.1)


def test_two_runs_further_apart_stay_separate_and_are_numbered_in_order():
    result = run("violin", (1.0, {"elbow_angle": 10.0}), (0.7, {}), (1.0, {"elbow_angle": 10.0}), take_id="take9")
    assert [f["id"] for f in result["flags"]] == ["f:take9:1", "f:take9:2"]
    assert result["flags"][0]["end_s"] < result["flags"][1]["start_s"]


def test_flags_from_different_rules_are_numbered_by_start_time():
    result = run("violin", (1.5, {"torso_lean": 30.0}), (0.5, {}), (1.5, {"elbow_angle": 100.0}))
    assert [(f["id"], f["rule"]) for f in result["flags"]] == [("f:t1:1", "slouching"), ("f:t1:2", "violin_elbow_high")]


def test_peak_is_the_frame_furthest_past_the_threshold():
    frames = timeline((RELAXED_S, {}), (0.5, {"elbow_angle": 15.0}), (0.1, {"elbow_angle": 2.0}),
                      (0.5, {"elbow_angle": 15.0}))
    [flag] = analyse(frames, "violin", "t1")["flags"]
    assert flag["peak_s"] == pytest.approx(RELAXED_S + 0.5)
    assert flag["value"] == pytest.approx(15.0)  # median of the run


def test_confidence_is_mean_visibility_of_the_landmarks_used():
    frames = timeline((RELAXED_S, {}), (1.5, {"elbow_angle": 10.0}))
    for frame in frames[round(RELAXED_S / 0.1):]:
        frame["pose"][12][2] = frame["pose"][14][2] = 0.8
    [flag] = analyse(frames, "violin", "t1")["flags"]
    assert flag["confidence"] == pytest.approx(0.8)


def test_confidence_drops_with_the_share_of_frames_where_the_measure_was_present():
    frames = timeline((RELAXED_S, {}), (1.0, {"elbow_angle": 10.0}), (0.4, {"elbow_angle": 10.0}),
                      (1.0, {"elbow_angle": 10.0}))
    for frame in frames[round((RELAXED_S + 1.0) / 0.1):round((RELAXED_S + 1.4) / 0.1)]:
        frame["pose"][14][2] = 0.0  # elbow lost inside the run: the gap is closed but counts against confidence
    [flag] = analyse(frames, "violin", "t1")["flags"]
    assert flag["end_s"] == pytest.approx(RELAXED_S + 2.4, abs=0.1)
    assert flag["confidence"] < 0.9


def test_shoulders_raised_is_judged_against_the_baseline():
    frames = timeline((2.0, {"neck_ratio": 0.6}), (2.0, {"neck_ratio": 0.4}))
    result = analyse(frames, "violin", "t1")
    assert result["baseline"]["neck_ratio"] == pytest.approx(0.6)
    assert result["baseline"]["head_drop"] == pytest.approx(-0.05)
    assert result["baseline"]["defaulted"] is False
    [flag] = result["flags"]
    assert flag["rule"] == "shoulders_raised"
    assert flag["start_s"] == pytest.approx(2.0, abs=0.1)
    assert flag["threshold"] == pytest.approx(0.75 * 0.6)
    assert flag["severity"] == pytest.approx((0.45 - 0.4) / 0.2)


def test_few_baseline_frames_use_the_defaults_and_say_so():
    early = [make_frame(i * 0.1, neck_ratio=0.8) for i in range(4)]
    late = [make_frame(5.0 + i * 0.1, neck_ratio=0.5) for i in range(30)]
    result = analyse(early + late, "violin", "t1")
    assert result["baseline"] == {"neck_ratio": config.DEFAULT_NECK_RATIO, "head_drop": config.DEFAULT_HEAD_DROP,
                                  "defaulted": True}
    assert result["flags"] == []  # 0.5 is above 0.75 x the default 0.55; 0.75 x a measured 0.8 would have flagged it


def test_five_baseline_frames_are_enough():
    early = [make_frame(i * 0.1, neck_ratio=0.8) for i in range(config.BASELINE_MIN_FRAMES)]
    late = [make_frame(5.0 + i * 0.1, neck_ratio=0.5) for i in range(30)]
    result = analyse(early + late, "violin", "t1")
    assert result["baseline"]["defaulted"] is False
    assert result["baseline"]["neck_ratio"] == pytest.approx(0.8)
    assert [f["rule"] for f in result["flags"]] == ["shoulders_raised"]


def test_hips_hidden_skips_the_torso_rule_and_the_neck_fallback_still_runs():
    hidden = {"hip_visibility": 0.2}
    result = run_all("violin", (2.0, hidden), (2.0, {**hidden, "neck_ratio": 0.45, "head_drop": 0.2}))
    assert result["rules_skipped"] == [{"rule": "slouching", "reason": "not_visible"}]
    [flag] = result["flags"]
    assert flag["rule"] == "slouching"
    assert flag["unit"] == "ratio" and flag["direction"] == "low"
    assert flag["threshold"] == pytest.approx(0.85 * 0.55)
    assert flag["start_s"] == pytest.approx(2.0, abs=0.1)


def test_neck_fallback_needs_the_head_drop_too():
    hidden = {"hip_visibility": 0.2}
    result = run_all("violin", (3.0, {**hidden, "neck_ratio": 0.45}))
    assert result["rules_skipped"] == [{"rule": "slouching", "reason": "not_visible"}]
    assert result["flags"] == []


def test_hidden_hips_never_flag_the_torso_rule():
    result = run_all("violin", (4.0, {"hip_visibility": 0.2, "torso_lean": 30.0}))
    assert result["flags"] == []


def test_trumpet_with_hidden_hips_skips_slouching_and_pinned_elbows():
    result = run_all("trumpet", (4.0, {"hip_visibility": 0.2, "elbow_gap_left": 0.0}))
    assert result["rules_skipped"] == [{"rule": "slouching", "reason": "not_visible"},
                                       {"rule": "trumpet_elbows_pinned", "reason": "not_visible"}]
    assert result["flags"] == []


def test_violin_without_a_hand_skips_the_wrist_rule():
    frames = timeline((RELAXED_S, {}), (2.0, {"wrist_bend": 50.0}))
    for frame in frames:
        frame["left_hand"] = None
    result = analyse(frames, "violin", "t1")
    assert result["rules_skipped"] == [{"rule": "violin_wrist_collapsed", "reason": "not_visible"}]
    assert result["flags"] == []


def test_a_take_with_no_tracked_person_skips_every_rule():
    frames = [{"t": i * 0.1, "pose": None, "left_hand": None, "right_hand": None} for i in range(30)]
    result = analyse(frames, "violin", "t1")
    assert result["flags"] == []
    assert result["baseline"]["defaulted"] is True
    assert {s["rule"] for s in result["rules_skipped"]} == {
        "violin_elbow_low", "violin_elbow_high", "violin_wrist_collapsed", "shoulders_raised", "slouching"}


def test_no_frames_gives_an_empty_result():
    result = analyse([], "trumpet", "t1")
    assert result["flags"] == []
    assert result["baseline"]["defaulted"] is True


def test_relaxed_player_has_no_flags_on_either_instrument():
    for instrument in ("violin", "trumpet"):
        result = run(instrument, (4.0, {}))
        assert result["flags"] == [] and result["rules_skipped"] == []


def test_unknown_instrument_is_refused_with_a_clear_message():
    with pytest.raises(ValueError, match="unknown instrument 'cello'"):
        analyse(timeline((1.0, RELAXED)), "cello", "t1")
