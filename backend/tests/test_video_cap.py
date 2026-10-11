"""Unit tests for scripts/video_cap: the default cap, the analysis window, and stopping once the video-time limit is passed (no real video)."""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import video_cap  # noqa: E402
from video_cap import MAX_VIDEO_SECONDS, add_max_seconds_argument, analysis_window, track_video_capped  # noqa: E402


def _parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_max_seconds_argument(parser)
    return parser.parse_args(list(argv))


def _fake_track_video(times: list[float], consumed: list[float]):
    """A track_video stand-in that feeds on_frame one 640x480 frame per time and records the times it was asked to process."""
    def fake(video, with_hands, time_limit_s, on_frame):
        for seconds in times:
            on_frame(np.zeros((480, 640, 3), dtype=np.uint8), seconds, {"pose": [[0.5, 0.5, 1.0]]})
            consumed.append(seconds)
    return fake


def test_default_cap_is_290_seconds():
    assert MAX_VIDEO_SECONDS == 290
    assert _parse().max_seconds == 290


def test_flag_takes_a_number_and_zero():
    assert _parse("--max-seconds", "60.5").max_seconds == 60.5
    assert _parse("--max-seconds", "0").max_seconds == 0


@pytest.mark.parametrize("bad", ["-1", "abc", "nan"])
def test_flag_rejects_a_bad_value_with_a_clear_message(bad, capsys):
    with pytest.raises(SystemExit):
        _parse("--max-seconds", bad)
    assert "--max-seconds" in capsys.readouterr().err


def test_help_says_zero_means_no_limit():
    parser = argparse.ArgumentParser()
    add_max_seconds_argument(parser)
    assert "0 means no limit" in parser.format_help().replace("\n", " ")


@pytest.mark.parametrize("cap_s,max_seconds,expected", [(120, 290, 120), (120, 60, 60), (400, 290, 290), (120, 120, 120)])
def test_window_is_the_smaller_of_cap_and_max(cap_s, max_seconds, expected):
    assert analysis_window(cap_s, max_seconds) == expected


def test_zero_max_seconds_leaves_just_the_cap():
    assert analysis_window(120, 0) == 120
    assert math.isinf(video_cap.video_limit_s(0))


def test_tracking_stops_once_the_limit_is_passed(monkeypatch):
    consumed: list[float] = []
    monkeypatch.setattr(video_cap, "track_video", _fake_track_video([0.0, 5.0, 10.0, 10.2, 15.0], consumed))
    seen: list[float] = []

    track = track_video_capped(Path("clip.mp4"), 10.0, 900, on_frame=lambda bgr, seconds, frame: seen.append(seconds))

    assert [f["t"] for f in track.frames] == [0.0, 5.0, 10.0]  # a frame exactly at the limit is kept
    assert seen == [0.0, 5.0, 10.0]  # the caller's on_frame never sees a frame past the limit
    assert consumed == [0.0, 5.0, 10.0]  # and tracking was not asked to go on
    assert (track.width, track.height) == (640, 480)
    assert track.aspect == pytest.approx(640 / 480)


def test_no_limit_tracks_every_frame(monkeypatch):
    monkeypatch.setattr(video_cap, "track_video", _fake_track_video([0.0, 500.0, 5000.0], []))
    track = track_video_capped(Path("clip.mp4"), video_cap.video_limit_s(0), 900)
    assert [f["t"] for f in track.frames] == [0.0, 500.0, 5000.0]


def test_track_video_errors_propagate(monkeypatch):
    def broken(video, with_hands, time_limit_s, on_frame):
        raise RuntimeError("cannot open clip.mp4")

    monkeypatch.setattr(video_cap, "track_video", broken)
    with pytest.raises(RuntimeError, match="cannot open"):
        track_video_capped(Path("clip.mp4"), 10.0, 900)
