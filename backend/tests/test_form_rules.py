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
    ("shoulders_raised", "violin", {"neck_ratio": 0.45 * RELAXED["neck_ratio"]}, "both"),
    ("slouching", "violin", {"torso_lean": 30.0}, None),
    ("shoulders_raised", "trumpet", {"neck_ratio": 0.45 * RELAXED["neck_ratio"]}, "both"),
    ("slouching", "trumpet", {"torso_lean": 30.0, "elbow_gap_right": RELAXED["elbow_gap_right"]}, None),  # right elbow kept by the hip it follows
    ("trumpet_head_down", "trumpet", {"head_drop": 0.2}, None),
    ("trumpet_elbows_pinned", "trumpet", {"elbow_gap_left": 0.02}, "left"),
]
RULE_CASES = pytest.mark.parametrize("rule, instrument, bad, side", BREAKING, ids=[f"{b[1]}-{b[0]}" for b in BREAKING])


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
    frames = timeline((2.0, {"neck_ratio": 0.6}), (2.0, {"neck_ratio": 0.27}))
    result = analyse(frames, "violin", "t1")
    assert result["baseline"]["neck_ratio"] == pytest.approx(0.6)
    assert result["baseline"]["head_drop"] == pytest.approx(-0.05)
    assert result["baseline"]["defaulted"] is False
    [flag] = result["flags"]
    assert flag["rule"] == "shoulders_raised"
    assert flag["start_s"] == pytest.approx(2.0, abs=0.1)
    threshold = config.SHOULDERS_RAISED_RATIO * 0.6
    assert flag["threshold"] == pytest.approx(threshold)
    assert flag["severity"] == pytest.approx((threshold - 0.27) / config.SEVERITY_SPANS["shoulders_raised"])


def test_a_mild_neck_dip_and_a_loose_elbow_gap_are_not_flagged():
    baseline_neck = 0.6  # a neck long enough that 0.65 of it is above the fixed limit
    mild_neck = 0.65 * baseline_neck  # flagged when the threshold was 0.70 of the baseline
    frames = timeline((RELAXED_S, {"neck_ratio": baseline_neck}), (2.0, {"neck_ratio": mild_neck, "elbow_gap_left": 0.08}))
    assert analyse(frames, "trumpet", "t1")["flags"] == []


def test_few_baseline_frames_use_the_defaults_and_say_so():
    early = [make_frame(i * 0.1, neck_ratio=0.8) for i in range(4)]
    late = [make_frame(5.0 + i * 0.1, neck_ratio=0.4) for i in range(30)]
    result = analyse(early + late, "violin", "t1")
    assert result["baseline"] == {"neck_ratio": config.DEFAULT_NECK_RATIO, "head_drop": config.DEFAULT_HEAD_DROP,
                                  "defaulted": True}
    assert result["flags"] == []  # 0.4 is above the threshold on the default 0.55; the same threshold on a measured 0.8 would have flagged it


def test_five_baseline_frames_are_enough():
    early = [make_frame(i * 0.1, neck_ratio=0.8) for i in range(config.BASELINE_MIN_FRAMES)]
    late = [make_frame(5.0 + i * 0.1, neck_ratio=0.36) for i in range(30)]
    result = analyse(early + late, "violin", "t1")
    assert result["baseline"]["defaulted"] is False
    assert result["baseline"]["neck_ratio"] == pytest.approx(0.8)
    assert [f["rule"] for f in result["flags"]] == ["shoulders_raised"]


def test_hips_hidden_skips_the_torso_rule_and_the_neck_fallback_still_runs():
    hidden = {"hip_visibility": 0.2}
    result = run_all("violin", (2.0, hidden), (2.0, {**hidden, "neck_ratio": 0.35, "head_drop": 0.2}))
    assert result["rules_skipped"] == [{"rule": "slouching", "reason": "not_visible"}]
    [flag] = result["flags"]
    assert flag["rule"] == "slouching"
    assert flag["unit"] == "ratio" and flag["direction"] == "low"
    assert flag["threshold"] == pytest.approx(0.85 * 0.45)
    assert flag["start_s"] == pytest.approx(2.0, abs=0.1)


def test_neck_fallback_needs_the_head_drop_too():
    hidden = {"hip_visibility": 0.2}
    result = run_all("violin", (3.0, {**hidden, "neck_ratio": 0.35}))
    assert result["rules_skipped"] == [{"rule": "slouching", "reason": "not_visible"}]
    assert result["flags"] == []


def test_hidden_hips_never_flag_the_torso_rule():
    result = run_all("violin", (4.0, {"hip_visibility": 0.2, "torso_lean": 30.0}))
    assert result["flags"] == []


def test_trumpet_with_hidden_hips_skips_slouching_and_the_elbow_rules():
    result = run_all("trumpet", (4.0, {"hip_visibility": 0.2, "elbow_gap_left": 0.0}))
    assert result["rules_skipped"] == [{"rule": "slouching", "reason": "not_visible"},
                                       {"rule": "trumpet_elbows_pinned", "reason": "not_visible"},
                                       {"rule": "trumpet_elbows_wide", "reason": "not_visible"}]
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


def _as_wide_video(frame: dict, width: int, height: int) -> dict:
    """The same physical pose, as the normalised coordinates a width x height video would give (x shrinks by height / width)."""
    squeeze = height / width
    squeeze_x = lambda points: None if points is None else [[p[0] * squeeze, *p[1:]] for p in points]  # noqa: E731
    return {**frame, "pose": squeeze_x(frame["pose"]), "left_hand": squeeze_x(frame["left_hand"])}


def test_measures_do_not_depend_on_the_video_aspect_ratio():
    square = make_frame(0.0, elbow_angle=30.0, neck_ratio=0.6, torso_lean=12.0, elbow_gap_left=0.3, wrist_bend=25.0)
    wide = _as_wide_video(square, 1280, 720)
    expected = {n: r.value for n, r in frame_measures(square).items()}
    assert {n: r.value for n, r in frame_measures(wide, 1280 / 720).items()} == pytest.approx(expected)
    assert frame_measures(wide)["elbow_angle"].value != pytest.approx(expected["elbow_angle"], abs=1.0)  # unscaled is distorted


def test_analyse_gives_the_same_flags_at_1280x720_as_at_720x720():
    frames = timeline((RELAXED_S, {}), (2.0, {"elbow_angle": 10.0, "torso_lean": 30.0}))
    square = analyse(frames, "violin", "t1", width=720, height=720)
    wide = analyse([_as_wide_video(f, 1280, 720) for f in frames], "violin", "t1", width=1280, height=720)
    assert [f["rule"] for f in wide["flags"]] == ["violin_elbow_low", "slouching"]
    for wide_flag, square_flag in zip(wide["flags"], square["flags"]):
        for field in ("start_s", "end_s", "value", "threshold", "severity", "confidence"):
            assert wide_flag[field] == pytest.approx(square_flag[field])
    assert len(wide["flags"]) == len(square["flags"])


@pytest.mark.parametrize("width, height", [(1280, None), (None, 720), (0, 720), (1280, -1)])
def test_bad_video_size_is_refused_with_a_clear_message(width, height):
    with pytest.raises(ValueError, match="width and height must both be positive"):
        analyse(timeline((1.0, {})), "violin", "t1", width=width, height=height)


def test_trumpet_neck_fallback_flags_slouching_when_hips_are_hidden():
    hidden = {"hip_visibility": 0.2}
    result = run_all("trumpet", (2.0, hidden), (2.0, {**hidden, "neck_ratio": 0.35, "head_drop": 0.2}))
    assert {"rule": "slouching", "reason": "not_visible"} in result["rules_skipped"]
    assert [f["rule"] for f in result["flags"]] == ["slouching", "trumpet_head_down"]
