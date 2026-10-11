"""Form flags on the fault videos, with the fixed limits of LLD-4 change 11.

Usage (from the repo root): backend/.venv/Scripts/python backend/scripts/fault_flags.py [--max-seconds 290] [--limit N] [--only ID ...]

Reads testdata/youtube/fault_manifest.csv (made by fetch_youtube.py --list testdata/youtube/fault_candidates.csv) and, one video at
a time, tracks the first --max-seconds seconds (video_cap.py) at the app's sample rate (10 fps, no hands, no face) and judges them with
app.form.rules.analyse as a trumpet take, the way form.run does. AI is never called. Writes testdata/youtube/fault_flags.csv:
one row per flag, plus one row per video with no flag, with its view and its rules skipped as not_visible / not_for_view.
--only re-runs just those videos (for example with a longer --max-seconds); the other videos' rows stay as they were.
"""
import argparse
import csv
import gc
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))  # for app.*
sys.path.insert(0, str(Path(__file__).parent))  # for posture_stats

from app.form.rules import analyse  # noqa: E402
from video_cap import add_max_seconds_argument, track_video_capped, video_limit_s  # noqa: E402

YOUTUBE_DIR = Path(__file__).parents[2] / "testdata" / "youtube"
MANIFEST_CSV = YOUTUBE_DIR / "fault_manifest.csv"
VIDEOS_DIR = YOUTUBE_DIR / "fault_videos"
FLAGS_CSV = YOUTUBE_DIR / "fault_flags.csv"
FLAG_FIELDS = ["id", "status", "video_s", "analysed_s", "frames_tracked", "frames_sampled", "view", "view_ratio", "rules_skipped",
               "rule", "start_s", "end_s", "severity", "side"]
WALL_LIMIT_S = 900  # track_video's own wall-clock limit; far above what a capped video needs
TRUMPET = "trumpet"

log = logging.getLogger("fault_flags")


@dataclass
class VideoFlags:
    """The outcome for one video: `status` is "ok" or why it was not analysed."""
    video_id: str
    status: str = "ok"
    video_s: str = ""
    analysed_s: float = 0.0
    frames_sampled: int = 0
    frames_tracked: int = 0
    view: str = ""
    view_ratio: float | None = None
    rules_skipped: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)


def analyse_video(row: dict, limit_s: float) -> VideoFlags:
    """Track and judge one manifest row; a video that cannot be analysed comes back with its reason in `status`."""
    result = VideoFlags(row["id"], video_s=row["duration_s"])
    if row["status"] != "ok":
        result.status = f"download {row['status']}"
        return result
    video = VIDEOS_DIR / f"{row['id']}.mp4"
    if not video.exists():
        result.status = f"video file missing: {video.name} (run fetch_youtube.py --list testdata/youtube/fault_candidates.csv)"
        return result
    track = track_video_capped(video, limit_s, WALL_LIMIT_S)
    frames = track.frames
    result.frames_sampled = len(frames)
    result.frames_tracked = sum(1 for f in frames if f["pose"] is not None)
    result.analysed_s = round(frames[-1]["t"], 1) if frames else 0.0
    if not result.frames_tracked:
        result.status = "no person tracked in any sampled frame"
        return result
    analysis = analyse(frames, TRUMPET, row["id"], width=track.width, height=track.height)
    result.view, result.view_ratio = analysis["view"], analysis["view_ratio"]
    result.rules_skipped, result.flags = analysis["rules_skipped"], analysis["flags"]
    return result


def csv_rows(result: VideoFlags) -> list[dict]:
    """One row per flag; a video with no flag (or no analysis) gets a single row with the flag columns empty."""
    skipped = "; ".join(f"{s['rule']}:{s['reason']}" for s in result.rules_skipped)
    base = {"id": result.video_id, "status": result.status, "video_s": result.video_s, "analysed_s": result.analysed_s,
            "frames_tracked": result.frames_tracked, "frames_sampled": result.frames_sampled, "view": result.view,
            "view_ratio": result.view_ratio, "rules_skipped": skipped}
    if not result.flags:
        return [base]
    return [{**base, "rule": f["rule"], "start_s": round(f["start_s"], 1), "end_s": round(f["end_s"], 1), "severity": round(f["severity"], 2), "side": f["side"]}
            for f in result.flags]


def run_one(row: dict, limit_s: float) -> VideoFlags:
    try:
        return analyse_video(row, limit_s)
    except Exception as error:  # one video failing (unreadable file, MediaPipe error) is recorded and the run goes on
        log.exception("%s failed", row["id"])
        return VideoFlags(row["id"], status=f"analysis error: {type(error).__name__}: {error}", video_s=row["duration_s"])


def kept_rows(rerun_ids: set[str]) -> list[dict]:
    """The rows already in fault_flags.csv for videos that are not being re-run."""
    if not FLAGS_CSV.exists():
        return []
    with FLAGS_CSV.open(encoding="utf-8", newline="") as f:
        return [row for row in csv.DictReader(f) if row["id"] not in rerun_ids]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_max_seconds_argument(parser)
    parser.add_argument("--limit", type=int, help="only the first N manifest rows")
    parser.add_argument("--only", nargs="+", help="only these video ids")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with MANIFEST_CSV.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if not args.only or r["id"] in args.only][:args.limit]
    kept = kept_rows({r["id"] for r in rows}) if args.only else []  # --only re-runs those videos and leaves the other rows as they were
    with FLAGS_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FLAG_FIELDS)
        writer.writeheader()
        writer.writerows(kept)
        for number, row in enumerate(rows, 1):
            result = run_one(row, video_limit_s(args.max_seconds))
            log.info("[%d/%d] %s: %s, %d flags", number, len(rows), row["id"], result.status if result.status != "ok" else result.view, len(result.flags))
            writer.writerows(csv_rows(result))
            f.flush()  # each video's rows reach the disk as soon as it is done
            gc.collect()
    log.info("wrote %s", FLAGS_CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
