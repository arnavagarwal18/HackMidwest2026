"""Unit tests for scripts/posture_stats: percentiles, the bell-angle proxy and the results section, on synthetic landmarks."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from app.form.measures import frame_measures  # noqa: E402
from posture_stats import VideoStats, stats_rows  # noqa: E402
from posture_stats_measures import BELL_PROXY, measure_specs, percentiles  # noqa: E402
from posture_stats_report import HEADING, build_section, write_results_section  # noqa: E402

UNUSED = [0.0, 0.0, 0.0]


def _pose(**points) -> list[list[float]]:
    """A 25-landmark pose, every point invisible except the named ones ({index: (x, y)}, visibility 1)."""
    pose = [list(UNUSED) for _ in range(25)]
    for index, (x, y) in points.items():
        pose[int(index.removeprefix("p"))] = [x, y, 1.0]
    return pose


def _bell(view: str, pose: list[list[float]]) -> float | None:
    return frame_measures({"pose": pose}, 1.0, measure_specs(view, "left"))[BELL_PROXY].value


def _side_pose(wrist_y: float, nose_x: float = 0.6) -> list[list[float]]:
    """Mouth at (0.6, 0.3); both wrists at x 0.8 and the given y; the near (left) ear at x 0.5; nose at nose_x."""
    return _pose(p0=(nose_x, 0.3), p7=(0.5, 0.3), p9=(0.6, 0.3), p10=(0.6, 0.3), p15=(0.8, wrist_y), p16=(0.8, wrist_y))


def test_percentiles_of_one_to_a_hundred():
    result = percentiles(list(range(1, 101)))
    assert result == pytest.approx({1: 1.99, 5: 5.95, 50: 50.5, 95: 95.05, 99: 99.01})


def test_percentiles_of_nothing_raises():
    with pytest.raises(ValueError, match="no values"):
        percentiles([])


@pytest.mark.parametrize("wrist_y,expected", [(0.3, 0.0), (0.1, 45.0), (0.5, -45.0)])
def test_side_bell_is_degrees_above_horizontal(wrist_y, expected):
    assert _bell("side", _side_pose(wrist_y)) == pytest.approx(expected)


def test_side_bell_is_the_same_facing_either_way():
    facing_right = _bell("side", _side_pose(0.1))
    mirrored = _pose(p0=(0.4, 0.3), p7=(0.5, 0.3), p9=(0.4, 0.3), p10=(0.4, 0.3), p15=(0.2, 0.1), p16=(0.2, 0.1))
    assert _bell("side", mirrored) == pytest.approx(facing_right)


def test_side_bell_is_missing_when_a_wrist_is_not_visible():
    pose = _side_pose(0.1)
    pose[16][2] = 0.1
    assert _bell("side", pose) is None


def test_front_bell_is_wrist_drop_over_shoulder_width():
    pose = _pose(p9=(0.48, 0.3), p10=(0.52, 0.3), p11=(0.6, 0.5), p12=(0.4, 0.5), p15=(0.55, 0.5), p16=(0.45, 0.5))
    assert _bell("front", pose) == pytest.approx(0.2 / 0.2)


def test_unknown_view_is_rejected():
    with pytest.raises(ValueError, match="view must be"):
        measure_specs("above", "left")


def _stats(video_id: str, view: str, values: list[float]) -> VideoStats:
    return VideoStats(video_id, view=view, view_ratio=1.0, frames_sampled=20, frames_tracked=20, values={BELL_PROXY: values})


def test_rows_carry_percentiles_and_skip_reasons():
    used = stats_rows(_stats("abc", "side", [float(v) for v in range(1, 101)]))
    assert used[0]["measure"] == BELL_PROXY and used[0]["frames_used"] == 100 and used[0]["p50"] == 50.5
    skipped = stats_rows(VideoStats("xyz", skip_reason="no visible player"))
    assert skipped == [{"id": "xyz", "view": "", "view_ratio": None, "frames_sampled": 0, "frames_tracked": 0,
                        "skip_reason": "no visible player"}]


def test_section_pools_per_view_and_lists_skips(tmp_path):
    all_stats = [_stats("a", "side", [0.0, 10.0]), _stats("b", "side", [20.0, 30.0]), VideoStats("c", skip_reason="download failed")]
    section = build_section(all_stats, 5, 120)
    assert "used: 2 (0 front, 2 side); skipped: 1" in section
    assert "| bell_proxy | 2 | 4 | 0.30 |" in section  # pooled p1 of 0, 10, 20, 30
    assert "| c | download failed |" in section

    results = tmp_path / "RESULTS.md"
    results.write_text("# Title\n\n" + HEADING + "\nold text\n\n## Later section\nkept\n", encoding="utf-8")
    write_results_section(results, all_stats, 5, 120)
    text = results.read_text(encoding="utf-8")
    assert "old text" not in text and "## Later section\nkept" in text and text.count(HEADING) == 1
