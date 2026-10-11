"""What the form rules measured inside the answer-key windows of one fault video, to see why a keyed fault was missed.

Usage (from the repo root): backend/.venv/bin/python backend/scripts/fault_miss_measures.py ID [--fps 5] [--max-seconds 290] [--window START END]

Run one video per process. It tracks the video the way fault_flags.py does (video_cap.py), then for each key of ID in
testdata/youtube/fault_keys.csv and for each trumpet rule of the key's rule name (in the front and the side view, with
`active` saying which one the detected view runs) summarises the rule's measure over the key's times +- its slack:
the baseline, the limit the rule used, the measure's spread, the longest run past the limit and the episodes the rule made.
Rows for ID replace its old rows in testdata/youtube/fault_miss_measures.csv.

--window START END tracks only the first 6 s (for the baseline) and START-5 s to END+5 s, cut out with ffmpeg, so a key
far into a long video stays inside the memory cap; frame times are mapped back to the original video's.
"""
import argparse
import csv
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import median

import imageio_ffmpeg
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))  # for app.*
sys.path.insert(0, str(Path(__file__).parent))

from app.form import config  # noqa: E402
from app.form.episodes import Sample, find_episodes, frame_interval  # noqa: E402
from app.form.measures import NOSE, Baseline, aspect_ratio, compute_baseline, frame_measures  # noqa: E402
from app.form.rules import RULES, TRUMPET, Rule, _sample, _view_specs  # noqa: E402
from app.form.side_measures import with_side_baseline  # noqa: E402
from app.form.view import SIDE, detect_view  # noqa: E402
from fault_flags import VIDEOS_DIR, WALL_LIMIT_S, YOUTUBE_DIR  # noqa: E402
from fault_flags_report import KEYS_CSV, read_csv  # noqa: E402
from video_cap import add_max_seconds_argument, track_video_capped, video_limit_s  # noqa: E402

MEASURES_CSV = YOUTUBE_DIR / "fault_miss_measures.csv"
FIELDS = ["id", "key_rule", "key_start_s", "key_end_s", "slack_s", "view", "view_ratio", "rule_view", "active", "measure", "direction",
          "baseline", "baseline_defaulted", "baseline_from_first_pose", "limit", "frames", "valid_frames", "median", "tail", "extreme", "past_frames",
          "longest_past_run_s", "episodes", "longest_episode_s", "visibility_median", "first_pose_s", "nose_x_median"]
LEAD_S = 6  # seconds from the start of the video kept with --window, for the baseline (first BASELINE_SECONDS)
PAD_S = 5  # seconds kept either side of the --window
BASELINE_ATTRIBUTE = {"head_drop": "head_drop", "head_pitch": "head_pitch", "neck_ratio": "neck_ratio", "neck_side": "neck_side"}

log = logging.getLogger("fault_miss_measures")


class MeasuresError(Exception):
    """A problem the user can fix; its message says how."""


@dataclass(frozen=True)
class TimeMap:
    """Maps a time in the (maybe cut) video to the original video's: the first LEAD_S seconds are kept as they are, the rest is shifted."""
    cut_from_s: float | None = None

    def original(self, seconds: float) -> float:
        if self.cut_from_s is None or seconds < LEAD_S:
            return seconds
        return seconds - LEAD_S + self.cut_from_s


def cut_window(video: Path, start_s: float, end_s: float, out: Path) -> TimeMap:
    """Write to `out` the first LEAD_S seconds of `video` followed by [start_s - PAD_S, end_s + PAD_S] (video only)."""
    from_s = max(start_s - PAD_S, LEAD_S)
    graph = (f"[0:v]trim=0:{LEAD_S},setpts=PTS-STARTPTS[a];[0:v]trim={from_s}:{end_s + PAD_S},setpts=PTS-STARTPTS[b];"
             "[a][b]concat=n=2:v=1:a=0[v]")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(video), "-filter_complex", graph, "-map", "[v]", str(out)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise MeasuresError(f"ffmpeg could not cut {video.name} to {from_s}-{end_s + PAD_S} s: {result.stderr.strip()[-300:]}")
    return TimeMap(from_s)


def longest_run_s(samples: list[Sample], interval: float) -> float:
    """Seconds of the longest stretch of consecutive frames past the limit (excess above 0)."""
    longest = current = 0
    for sample in samples:
        current = current + 1 if sample.excess is not None and sample.excess > 0 else 0
        longest = max(longest, current)
    return round(longest * interval, 2)


def window_stats(rule: Rule, times: list[float], samples: list[Sample], start_s: float, end_s: float) -> dict:
    """The rule's samples with start_s <= t <= end_s: counts, spread of the measure, longest run past the limit, episodes made."""
    inside = [(t, s) for t, s in zip(times, samples) if start_s <= t <= end_s]
    interval = frame_interval(times)
    window_times, window_samples = [t for t, _ in inside], [s for _, s in inside]
    values = [s.value for s in window_samples if s.value is not None]
    episodes = find_episodes(window_times, window_samples) if window_times else []
    extreme = (max if rule.direction == "high" else min)(values) if values else None
    tail_percentile = 90 if rule.direction == "high" else 10  # the tail on the side of the limit
    return {"frames": len(inside), "valid_frames": len(values),
            "median": median(values) if values else None, "tail": float(np.percentile(values, tail_percentile)) if values else None,
            "extreme": extreme, "past_frames": sum(1 for s in window_samples if s.excess is not None and s.excess > 0),
            "longest_past_run_s": longest_run_s(window_samples, interval), "episodes": len(episodes),
            "longest_episode_s": round(max((e.end_s - e.start_s for e in episodes), default=0.0), 2),
            "visibility_median": median(s.visibility for s in window_samples) if window_samples else None}


def window_nose_x(frames: list[dict], start_s: float, end_s: float) -> float | None:
    """Median across-the-frame position (0 left, 1 right) of the tracked nose in the window: which person was tracked."""
    xs = [f["pose"][NOSE][0] for f in frames if start_s <= f["t"] <= end_s and f.get("pose")]
    return median(xs) if xs else None


def view_baselines(frames: list[dict], readings: list[dict], view: str) -> Baseline:
    baseline = compute_baseline(frames, readings)
    return with_side_baseline(baseline, frames, readings) if view == SIDE else baseline


def view_samples(frames: list[dict], width: int, height: int, view: str, rules: list[Rule],
                 first_pose_s: float) -> tuple[Baseline, Baseline, list[list[Sample]]]:
    """(baseline, the baseline taken from the first BASELINE_SECONDS after the first tracked frame, each rule's samples).

    The first is what analyse() uses when it judges the take in `view`; the second shows what a video that opens on a
    title card (nobody tracked in its first seconds, so the baseline is defaulted) would have given.
    """
    aspect = aspect_ratio(width, height)
    readings = [frame_measures(f, aspect, _view_specs(view, frames)) for f in frames]
    shifted = [{**f, "t": f["t"] - first_pose_s} for f in frames]
    baseline, late = view_baselines(frames, readings, view), view_baselines(shifted, readings, view)
    return baseline, late, [[_sample(rule, r, baseline) for r in readings] for rule in rules]


def key_rows(video_id: str, frames: list[dict], width: int, height: int, keys: list[dict]) -> list[dict]:
    """One row per key, trumpet rule of the key's name and view: the measure over the key's window (times +- slack)."""
    view, view_ratio = detect_view(frames, aspect_ratio(width, height))
    times = [f["t"] for f in frames]
    first_pose_s = min((f["t"] for f in frames if f.get("pose")), default=None)
    rows = []
    for key in keys:
        rules = [r for r in RULES if r.name == key["rule"] and TRUMPET in r.instruments and r.fallback_for is None]
        if not rules:
            raise MeasuresError(f"{video_id}: no trumpet rule named {key['rule']!r} to measure (check {KEYS_CSV.name})")
        slack, start, end = float(key["slack_s"]), float(key["start_s"]), float(key["end_s"])
        for rule_view in sorted({v for r in rules for v in r.views}):
            view_rules = [r for r in rules if rule_view in r.views]
            baseline, late, samples = view_samples(frames, width, height, rule_view, view_rules, first_pose_s or 0.0)
            for rule, rule_samples in zip(view_rules, samples):
                limit = rule.threshold(baseline)
                stats = window_stats(rule, times, rule_samples, start - slack, end + slack)
                stats.update(first_pose_s=first_pose_s, nose_x_median=window_nose_x(frames, start - slack, end + slack))
                rows.append({"id": video_id, "key_rule": key["rule"], "key_start_s": start, "key_end_s": end, "slack_s": slack,
                             "view": view, "view_ratio": view_ratio, "rule_view": rule_view, "active": rule_view == view,
                             "measure": rule.measure, "direction": rule.direction,
                             "baseline": getattr(baseline, BASELINE_ATTRIBUTE.get(rule.measure, "_none"), None),
                             "baseline_from_first_pose": getattr(late, BASELINE_ATTRIBUTE.get(rule.measure, "_none"), None),
                             "baseline_defaulted": baseline.defaulted, "limit": limit, **stats})
    return rows


def rounded(row: dict) -> dict:
    return {k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()}


def write_rows(video_id: str, rows: list[dict]) -> None:
    """Replace video_id's rows in MEASURES_CSV with `rows`, keeping the other videos' rows."""
    kept = [r for r in read_csv(MEASURES_CSV) if r["id"] != video_id] if MEASURES_CSV.exists() else []
    with MEASURES_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(kept)
        writer.writerows(rounded(r) for r in rows)


def measure_video(video_id: str, fps: int, max_seconds: float, window: tuple[float, float] | None) -> list[dict]:
    keys = [k for k in read_csv(KEYS_CSV) if k["id"] == video_id]
    if not keys:
        raise MeasuresError(f"{video_id} has no rows in {KEYS_CSV.name}")
    video = VIDEOS_DIR / f"{video_id}.mp4"
    if not video.exists():
        raise MeasuresError(f"video file missing: {video} (download it with fetch_youtube.py --list testdata/youtube/fault_candidates.csv)")
    time_map, cut = TimeMap(), None
    if window:
        keys = [k for k in keys if float(k["end_s"]) + float(k["slack_s"]) >= window[0] - PAD_S and float(k["start_s"]) - float(k["slack_s"]) <= window[1] + PAD_S]
        if not keys:
            raise MeasuresError(f"{video_id} has no key inside --window {window[0]:g} {window[1]:g} (+-{PAD_S} s)")
        cut = VIDEOS_DIR / f"{video_id}_window.mp4"  # next to the video, in a git-ignored folder
        time_map = cut_window(video, *window, cut)
    config.FPS = fps  # the tracker samples at config.FPS; the offline runs use a lower rate to bound memory
    try:
        track = track_video_capped(cut or video, video_limit_s(max_seconds), WALL_LIMIT_S)
    finally:
        if cut:
            cut.unlink(missing_ok=True)
    frames = [{**f, "t": time_map.original(f["t"])} for f in track.frames]
    if not any(f["pose"] for f in frames):
        raise MeasuresError(f"{video_id}: no person tracked in any sampled frame")
    return key_rows(video_id, frames, track.width, track.height, keys)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("id", help="one video id from fault_keys.csv")
    parser.add_argument("--fps", type=int, default=5, help="frames sampled per second of video (default 5)")
    parser.add_argument("--window", nargs=2, type=float, metavar=("START", "END"), help="only the first 6 s and START-5 to END+5 s")
    add_max_seconds_argument(parser)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        rows = measure_video(args.id, args.fps, args.max_seconds, tuple(args.window) if args.window else None)
        write_rows(args.id, rows)
    except (MeasuresError, OSError) as error:
        log.error("%s", error)
        return 1
    log.info("wrote %d rows for %s to %s", len(rows), args.id, MEASURES_CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())
