"""The offline scripts' video-length cap: no run processes more than MAX_VIDEO_SECONDS of any video by default (it bounds memory).

Each script registers the flag with add_max_seconds_argument() and passes its value to track_video_capped(), which stops
tracking once the video time passes the limit.
"""
import argparse
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))  # for app.*

from app.form.track import track_video  # noqa: E402

MAX_VIDEO_SECONDS = 290  # 4:50

log = logging.getLogger("video_cap")


class CapReached(Exception):
    """Raised from track_video's per-frame callback to stop once the video-time limit has been passed."""


@dataclass
class CappedTrack:
    frames: list[dict] = field(default_factory=list)  # the app's {t, pose, ...} dicts, in video-time order
    width: int = 0  # full-resolution pixel size of the first frame; 0 when no frame was tracked
    height: int = 0

    @property
    def aspect(self) -> float:
        return self.width / self.height if self.height else 1.0


def _non_negative_seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number of seconds; give e.g. 290, or 0 for no limit")
    if value < 0 or math.isnan(value):
        raise argparse.ArgumentTypeError(f"{text} is not allowed; give a number of seconds of at least 0 (0 means no limit)")
    return value


def add_max_seconds_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-seconds", type=_non_negative_seconds, default=MAX_VIDEO_SECONDS,
                        help=f"process at most this many seconds of each video (default {MAX_VIDEO_SECONDS}, which keeps memory use down); "
                             "0 means no limit, for deliberate full-length runs on other machines")


def video_limit_s(max_seconds: float) -> float:
    """The video-time limit for a --max-seconds value: infinity when it is 0 (no limit)."""
    return max_seconds if max_seconds > 0 else math.inf


def analysis_window(cap_s: float, max_seconds: float) -> float:
    """Seconds of video to analyse: cap_s, or less when --max-seconds is smaller (0 leaves just cap_s)."""
    return min(cap_s, video_limit_s(max_seconds))


def track_video_capped(video: Path, limit_s: float, wall_limit_s: float, on_frame=None, with_hands: bool = False) -> CappedTrack:
    """Track video until its video time passes limit_s (use video_limit_s() or analysis_window()); on_frame is passed each frame within it.

    wall_limit_s is track_video's own wall-clock limit. Errors from track_video (unreadable video, MediaPipe) propagate.
    """
    track = CappedTrack()

    def collect(full_bgr, seconds: float, frame: dict) -> None:
        if seconds > limit_s:
            raise CapReached
        if not track.frames:
            track.height, track.width = full_bgr.shape[:2]
        track.frames.append({"t": seconds, **frame})
        if on_frame is not None:
            on_frame(full_bgr, seconds, frame)

    try:
        track_video(video, with_hands=with_hands, time_limit_s=wall_limit_s, on_frame=collect)
    except CapReached:
        log.info("%s: stopped at the %g s video limit (--max-seconds 0 removes it)", video.name, limit_s)
    return track
