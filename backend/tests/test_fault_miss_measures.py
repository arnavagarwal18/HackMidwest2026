import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import fault_miss_measures as fmm  # noqa: E402
from app.form.episodes import Sample  # noqa: E402
from app.form.rules import RULES  # noqa: E402

FRAME_S = 0.2  # 5 fps


def pose(nose_y: float) -> list[list[float]]:
    """A front-facing player: shoulders 0.2 wide at y 0.5, ears at y 0.40, the nose at nose_y (head_drop = (nose_y - 0.40) / 0.2)."""
    landmarks = [[0.5, 0.5, 1.0] for _ in range(25)]
    landmarks[0] = [0.5, nose_y, 1.0]
    landmarks[7], landmarks[8] = [0.45, 0.40, 1.0], [0.55, 0.40, 1.0]
    landmarks[11], landmarks[12] = [0.4, 0.5, 1.0], [0.6, 0.5, 1.0]
    landmarks[23], landmarks[24] = [0.4, 0.9, 1.0], [0.6, 0.9, 1.0]
    return landmarks


def frames_with_head_down(first_s: float, last_s: float, seconds: float = 30) -> list[dict]:
    """Frames at 5 fps; the head is level (drop 0.1) except from first_s to last_s, where it is far down (drop 0.9)."""
    times = [round(i * FRAME_S, 6) for i in range(int(seconds / FRAME_S))]
    return [{"t": t, "pose": pose(0.58 if first_s <= t <= last_s else 0.42), "left_hand": None, "right_hand": None} for t in times]


def head_down_key(start: float, end: float, slack: float = 2) -> dict:
    return {"id": "v", "rule": "trumpet_head_down", "start_s": str(start), "end_s": str(end), "slack_s": str(slack)}


def test_time_map_keeps_the_lead_and_shifts_the_cut_part_back_to_the_original_time():
    time_map = fmm.TimeMap(cut_from_s=470)
    assert time_map.original(3.0) == 3.0
    assert time_map.original(fmm.LEAD_S + 8.0) == 478.0
    assert fmm.TimeMap().original(100.0) == 100.0


def test_longest_run_counts_the_longest_stretch_of_frames_past_the_limit():
    samples = [Sample(1, e, 1.0) for e in (-1, 1, 1, -1, 1, 1, 1, None, 1)]
    assert fmm.longest_run_s(samples, 0.2) == 0.6


def test_a_head_drop_inside_the_window_is_measured_past_the_limit_with_its_run_and_episode():
    frames = frames_with_head_down(10, 14)
    rows = fmm.key_rows("v", frames, 100, 100, [head_down_key(10, 14)])
    front = next(r for r in rows if r["rule_view"] == "front")
    assert (front["view"], front["active"], front["measure"]) == ("front", True, "head_drop")
    assert front["baseline"] == pytest.approx(0.1) and front["limit"] == pytest.approx(0.25)
    assert front["past_frames"] == 21 and front["longest_past_run_s"] == pytest.approx(4.2)
    assert front["episodes"] == 1 and front["longest_episode_s"] == pytest.approx(4.2)
    assert front["extreme"] == pytest.approx(0.9)


def test_the_rule_of_the_other_view_is_listed_too_and_marked_inactive():
    rows = fmm.key_rows("v", frames_with_head_down(10, 14), 100, 100, [head_down_key(10, 14)])
    assert {(r["rule_view"], r["active"]) for r in rows} == {("front", True), ("side", False)}


def test_a_level_head_leaves_no_frames_past_the_limit():
    rows = fmm.key_rows("v", frames_with_head_down(100, 200), 100, 100, [head_down_key(10, 14)])
    front = next(r for r in rows if r["rule_view"] == "front")
    assert front["past_frames"] == 0 and front["episodes"] == 0 and front["median"] == pytest.approx(0.1)


def test_a_key_after_the_end_of_the_frames_has_a_window_with_no_frames():
    rule = next(r for r in RULES if r.name == "trumpet_head_down")
    stats = fmm.window_stats(rule, [0.0, 0.2], [Sample(0.1, -1, 1.0)] * 2, 50, 60)
    assert stats["frames"] == 0 and stats["median"] is None and stats["episodes"] == 0


def test_a_key_naming_an_unknown_rule_is_an_error_that_names_the_rule():
    key = {**head_down_key(10, 14), "rule": "trumpet_no_such_rule"}
    with pytest.raises(fmm.MeasuresError, match="trumpet_no_such_rule"):
        fmm.key_rows("v", frames_with_head_down(10, 14), 100, 100, [key])


def test_a_video_with_no_keys_is_an_error_naming_the_keys_file(monkeypatch):
    monkeypatch.setattr(fmm, "read_csv", lambda path: [])
    with pytest.raises(fmm.MeasuresError, match="fault_keys.csv"):
        fmm.measure_video("nokeys", 5, 290, None)


def test_a_missing_video_file_is_an_error_that_says_how_to_download_it(monkeypatch, tmp_path):
    monkeypatch.setattr(fmm, "read_csv", lambda path: [head_down_key(1, 2) | {"id": "gone"}])
    monkeypatch.setattr(fmm, "VIDEOS_DIR", tmp_path)
    with pytest.raises(fmm.MeasuresError, match="fetch_youtube.py"):
        fmm.measure_video("gone", 5, 290, None)


def test_a_window_with_no_key_in_it_is_an_error(monkeypatch, tmp_path):
    (tmp_path / "far.mp4").write_bytes(b"")
    monkeypatch.setattr(fmm, "read_csv", lambda path: [head_down_key(1, 2) | {"id": "far"}])
    monkeypatch.setattr(fmm, "VIDEOS_DIR", tmp_path)
    with pytest.raises(fmm.MeasuresError, match="no key inside --window"):
        fmm.measure_video("far", 5, 290, (400, 420))


def test_writing_rows_replaces_the_videos_old_rows_and_keeps_the_others(monkeypatch, tmp_path):
    monkeypatch.setattr(fmm, "MEASURES_CSV", tmp_path / "m.csv")
    fmm.write_rows("a", [{"id": "a", "key_rule": "old"}])
    fmm.write_rows("b", [{"id": "b", "key_rule": "x"}])
    fmm.write_rows("a", [{"id": "a", "key_rule": "new"}])
    kept = fmm.read_csv(tmp_path / "m.csv")
    assert [(r["id"], r["key_rule"]) for r in kept] == [("b", "x"), ("a", "new")]
