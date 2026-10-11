"""Good-posture statistics from the approved YouTube trumpet videos (LLD-4 change 10).

Usage (from the repo root): backend/.venv/bin/python backend/scripts/posture_stats.py [--fps 5] [--cap-s 120] [--limit N]

Reads testdata/youtube/manifest.csv, and for each downloaded video (one at a time, the pose landmarker freed after each):
tracks it with app.form.track.track_video at --fps for the first --cap-s seconds of video, detects the view (front or side) with
app.form.view, skips it if no pose is found in more than 70% of the sampled frames, and takes the absolute (not baseline-relative)
posture measures of app.form.measures / side_measures plus the bell-angle proxy (defined in posture_stats_measures.py) on
every tracked frame. Writes testdata/youtube/posture_stats.csv (one row per video x measure: 1st/5th/50th/95th/99th percentiles), each video's rows as soon as it is done,
and the "Good-posture statistics (YouTube set)" section of testdata/RESULTS_form_runs.md.
"""
import argparse
import csv
import gc
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))  # for app.*
sys.path.insert(0, str(Path(__file__).parent))  # for the sibling posture_stats_* modules

from app.form import config  # noqa: E402
from app.form.measures import frame_measures  # noqa: E402
from app.form.track import track_video  # noqa: E402
from app.form.view import detect_view, near_side  # noqa: E402
from posture_stats_measures import PERCENTILES, measure_specs, percentiles  # noqa: E402
from posture_stats_report import write_results_section  # noqa: E402

YOUTUBE_DIR = Path(__file__).parents[2] / "testdata" / "youtube"
MANIFEST_CSV = YOUTUBE_DIR / "manifest.csv"
VIDEOS_DIR = YOUTUBE_DIR / "videos"
STATS_CSV = YOUTUBE_DIR / "posture_stats.csv"
RESULTS_MD = YOUTUBE_DIR.parent / "RESULTS_form_runs.md"
STATS_FIELDS = ["id", "view", "view_ratio", "measure", "frames_used", "frames_sampled", "frames_tracked",
                *(f"p{p}" for p in PERCENTILES), "skip_reason"]
DEFAULT_FPS, DEFAULT_CAP_S = 5, 120
MIN_TRACKED_FRACTION = 0.3  # no pose in more than 70% of the sampled frames: no visible player
MIN_MEASURE_FRAMES = 10  # a measure with fewer usable frames than this in a video is left out
WALL_LIMIT_S = 900  # track_video's own wall-clock limit; far above what a capped video needs

log = logging.getLogger("posture_stats")


class CapReached(Exception):
    """Raised from track_video's per-frame callback to stop once the video-time cap has been passed."""


@dataclass
class VideoStats:
    video_id: str
    skip_reason: str = ""
    view: str = ""
    view_ratio: float | None = None
    frames_sampled: int = 0
    frames_tracked: int = 0
    values: dict[str, list[float]] = field(default_factory=dict)  # measure -> its usable per-frame values
    short_measures: dict[str, int] = field(default_factory=dict)  # measure -> usable frames, when under MIN_MEASURE_FRAMES


def track_capped(video: Path, cap_s: float) -> tuple[list[dict], float]:
    """(frames, aspect): the tracked frames of the first cap_s seconds of video time (the app's {t, pose, ...} dicts)."""
    frames, aspects = [], []

    def collect(full_bgr, seconds: float, frame: dict) -> None:
        if seconds > cap_s:
            raise CapReached
        aspects.append(full_bgr.shape[1] / full_bgr.shape[0])
        frames.append({"t": seconds, **frame})

    try:
        track_video(video, with_hands=False, time_limit_s=WALL_LIMIT_S, on_frame=collect)
    except CapReached:
        pass
    return frames, aspects[0] if aspects else 1.0


def analyse_video(video_id: str, video: Path, cap_s: float) -> VideoStats:
    """Track one video and take its measures. A skipped video comes back with skip_reason set."""
    stats = VideoStats(video_id)
    frames, aspect = track_capped(video, cap_s)
    stats.frames_sampled = len(frames)
    stats.frames_tracked = sum(1 for f in frames if f["pose"] is not None)
    if stats.frames_tracked < MIN_TRACKED_FRACTION * stats.frames_sampled:
        stats.skip_reason = f"no visible player: pose in only {stats.frames_tracked} of {stats.frames_sampled} sampled frames"
        return stats
    stats.view, stats.view_ratio = detect_view(frames, aspect)
    specs = measure_specs(stats.view, near_side(frames))
    readings = [frame_measures(f, aspect, specs) for f in frames]
    for name in specs:
        values = [r[name].value for r in readings if r[name].value is not None]
        if len(values) >= MIN_MEASURE_FRAMES:
            stats.values[name] = values
        else:
            stats.short_measures[name] = len(values)
    return stats


def skipped(video_id: str, reason: str) -> VideoStats:
    return VideoStats(video_id, skip_reason=reason)


def stats_rows(stats: VideoStats) -> list[dict]:
    """The CSV rows of one video: one per measure, or a single row carrying the skip reason."""
    base = {"id": stats.video_id, "view": stats.view, "view_ratio": stats.view_ratio, "frames_sampled": stats.frames_sampled,
            "frames_tracked": stats.frames_tracked}
    if stats.skip_reason:
        return [{**base, "skip_reason": stats.skip_reason}]
    rows = [{**base, "measure": name, "frames_used": len(values), **{f"p{p}": round(v, 3) for p, v in percentiles(values).items()}}
            for name, values in stats.values.items()]
    rows += [{**base, "measure": name, "frames_used": n, "skip_reason": f"only {n} usable frames"} for name, n in stats.short_measures.items()]
    return rows


def process_manifest_row(row: dict, cap_s: float) -> VideoStats:
    video_id = row["id"]
    if row["status"] != "ok":
        return skipped(video_id, f"download {row['status']}")
    video = VIDEOS_DIR / f"{video_id}.mp4"
    if not video.exists():
        return skipped(video_id, f"video file missing: {video.name} (run fetch_youtube.py)")
    try:
        return analyse_video(video_id, video, cap_s)
    except Exception as e:  # any one video failing (unreadable file, MediaPipe error) is recorded and the run goes on
        log.exception("%s failed", video_id)
        return skipped(video_id, f"analysis error: {type(e).__name__}: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS, help="sample rate in frames per second of video")
    parser.add_argument("--cap-s", type=float, default=DEFAULT_CAP_S, help="analyse only the first N seconds of each video")
    parser.add_argument("--limit", type=int, help="only the first N manifest rows")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    config.FPS = args.fps  # track_video reads the sample rate from here; this script's own process only

    with MANIFEST_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))[:args.limit]
    all_stats = []
    with STATS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=STATS_FIELDS)
        writer.writeheader()
        for number, row in enumerate(rows, 1):
            stats = process_manifest_row(row, args.cap_s)
            log.info("[%d/%d] %s: %s", number, len(rows), row["id"], stats.skip_reason or f"{stats.view}, {stats.frames_tracked}/{stats.frames_sampled} frames")
            writer.writerows(stats_rows(stats))
            f.flush()  # each video's rows reach the disk as soon as it is done, so a crash loses nothing earlier
            all_stats.append(stats)
            gc.collect()  # the landmarker was closed by track_video; drop its frames before the next video
    write_results_section(RESULTS_MD, all_stats, args.fps, args.cap_s)
    log.info("wrote %s and the results section of %s", STATS_CSV, RESULTS_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
