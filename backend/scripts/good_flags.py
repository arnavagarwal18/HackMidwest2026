"""How often the trumpet form rules flag the good-posture YouTube videos (TEAM-24 review of the fixed limits, LLD-4 change 11).

Usage (from the repo root):
  backend/.venv/Scripts/python backend/scripts/good_flags.py [--fps 5] [--cap-s 120] [--set NAME=VALUE ...]
  backend/.venv/Scripts/python backend/scripts/good_flags.py --clips testdata/form/take5_ode_form_front.mp4 ... [--fps 10 --cap-s 0]

The videos are the ones posture_stats.csv used (a view and no skip reason). Each is tracked once (cached in
testdata/youtube/videos/tracks/, git-ignored), then judged twice with app.form.rules.analyse for the trumpet: with the config
as it is, and with every fixed limit switched off (the baseline rules alone). A rule's flags on a video are "caused by the
fixed limit" when the first run flags it and the second does not. --set NAME=VALUE overrides a config.py setting for what-if
runs (the cache makes them fast). Writes testdata/youtube/good_flags.csv (one row per video x rule that flagged) and prints
the per-rule counts. With --clips the given videos are judged instead and each one's flags are printed, nothing is written.
"""
import argparse
import csv
import json
import logging
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))  # for app.*
sys.path.insert(0, str(Path(__file__).parent))  # for posture_stats

from app.form import config  # noqa: E402
from app.form.rules import analyse  # noqa: E402
from posture_stats import DEFAULT_CAP_S, DEFAULT_FPS, VIDEOS_DIR, YOUTUBE_DIR, track_capped  # noqa: E402

STATS_CSV = YOUTUBE_DIR / "posture_stats.csv"
OUT_CSV = YOUTUBE_DIR / "good_flags.csv"
TRACKS_DIR = VIDEOS_DIR / "tracks"
OUT_FIELDS = ["id", "view", "baseline_defaulted", "rule", "direction", "flags", "flags_baseline_only", "caused_by_fixed_limit",
              "worst_value", "longest_run_s", "first_start_s"]
EXCLUDED = {  # videos whose flags are tracker noise, not posture (checked on frames at the flagged times, 2026-10-11)
    "03Y8iZdr5bE": "no player: the frames at the flagged times show the audience",
    "p0c4GJHLZvI": "orchestra, several trumpets in frame: the tracker follows a different player from moment to moment",
    "H0I1FjTeJ2w": "orchestra cut between sections, cropped at the waist: the tracked person is sometimes a woodwind player",
    "ZUZYoVw7moc": "orchestra, player partly behind the timpani and conductor, cropped at the hips or hem: pose jumps between people",
    "TvRuRdMzAPg": "cropped at the waist (hips invented by the tracker), pose found in 66% of frames; elbow, neck and bell readings swing",
}
FIXED_LIMITS_OFF = {  # config name -> the value that never breaks its rule
    "TRUMPET_HEAD_DROP_MAX": math.inf, "TRUMPET_NECK_RATIO_MIN": -math.inf, "TRUMPET_HEAD_PITCH_MAX": math.inf,
    "TRUMPET_NECK_SIDE_MIN": -math.inf, "TRUMPET_ELBOWS_WIDE_GAP": math.inf, "TRUMPET_BELL_HEIGHT_MIN": -math.inf,
    "TRUMPET_BELL_HEIGHT_MAX": math.inf, "TRUMPET_BELL_ANGLE_MAX": math.inf, "TRUMPET_BELL_ANGLE_MIN": -math.inf,
}

log = logging.getLogger("good_flags")


def good_video_ids() -> dict[str, str]:
    """{video id: view} of every video posture_stats.csv measured (the usable good videos)."""
    with STATS_CSV.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {row["id"]: row["view"] for row in rows if row["view"] and not row["skip_reason"]}


def tracked(name: str, video: Path, fps: float, cap_s: float) -> tuple[list[dict], float]:
    """(frames, aspect) of the video, from the cache when it holds them for this fps and cap."""
    cache = TRACKS_DIR / f"{name}_{fps:g}fps_{cap_s:g}s.json"
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
        return saved["frames"], saved["aspect"]
    config.FPS = fps
    frames, aspect = track_capped(video, cap_s or math.inf)
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"aspect": aspect, "frames": frames}), encoding="utf-8")
    return frames, aspect


def judge(frames: list[dict], aspect: float, video_id: str) -> dict:
    return analyse(frames, "trumpet", video_id, width=aspect, height=1)


def with_fixed_limits_off(frames: list[dict], aspect: float, video_id: str) -> dict:
    saved = {name: getattr(config, name) for name in FIXED_LIMITS_OFF}
    try:
        for name, value in FIXED_LIMITS_OFF.items():
            setattr(config, name, value)
        return judge(frames, aspect, video_id)
    finally:
        for name, value in saved.items():
            setattr(config, name, value)


def by_rule(analysis: dict) -> dict[str, list[dict]]:
    """The analysis' flags grouped by rule and direction (left and right elbows share one group)."""
    groups = defaultdict(list)
    for flag in analysis["flags"]:
        groups[f"{flag['rule']}|{flag['direction']}"].append(flag)
    return groups


def video_rows(video_id: str, frames: list[dict], aspect: float) -> list[dict]:
    """One row per rule that flagged the video, with or without the fixed limits."""
    with_limits, baseline_only = judge(frames, aspect, video_id), with_fixed_limits_off(frames, aspect, video_id)
    flagged, base = by_rule(with_limits), by_rule(baseline_only)
    rows = []
    for key in sorted(set(flagged) | set(base)):
        rule, direction = key.split("|")
        flags = flagged.get(key, [])
        values = [flag["value"] for flag in flags]
        rows.append({
            "id": video_id, "view": with_limits["view"], "baseline_defaulted": with_limits["baseline"]["defaulted"],
            "rule": rule, "direction": direction, "flags": len(flags), "flags_baseline_only": len(base.get(key, [])),
            "caused_by_fixed_limit": bool(flags) and key not in base,
            "worst_value": round(max(values) if direction == "high" else min(values), 3) if values else "",
            "longest_run_s": round(max(flag["end_s"] - flag["start_s"] for flag in flags), 1) if flags else "",
            "first_start_s": round(min(flag["start_s"] for flag in flags), 1) if flags else "",
        })
    return rows


def print_counts(rows: list[dict], total: int) -> None:
    """Per rule, view and direction: videos with any flag and videos flagged because of a fixed limit, with and without EXCLUDED."""
    counts = defaultdict(lambda: defaultdict(set))  # key -> {"any", "fixed", "any_kept", "fixed_kept"} -> video ids
    for row in rows:
        key = f"{row['rule']} ({row['view']}, {row['direction']})"
        kept = row["id"] not in EXCLUDED
        for name, hit in (("any", row["flags"]), ("fixed", row["caused_by_fixed_limit"])):
            if hit:
                counts[key][name].add(row["id"])
                if kept:
                    counts[key][name + "_kept"].add(row["id"])
    print(f"{'rule (view, direction)':44s} any flag: {total} | {total - len(EXCLUDED)} kept     caused by fixed limit: {total} | {total - len(EXCLUDED)} kept")
    for key in sorted(counts):
        c = counts[key]
        print(f"{key:44s} {len(c['any']):3d} | {len(c['any_kept']):3d}                      {len(c['fixed']):3d} | {len(c['fixed_kept']):3d}   {sorted(c['fixed_kept'])}")


def apply_overrides(settings: list[str]) -> None:
    for setting in settings:
        name, _, text = setting.partition("=")
        if not hasattr(config, name):
            raise SystemExit(f"--set {setting!r}: config.py has no setting {name!r}")
        setattr(config, name, float(text))


def run_good_set(fps: float, cap_s: float) -> int:
    views = good_video_ids()
    rows, missing = [], []
    for number, (video_id, view) in enumerate(views.items(), 1):
        video = VIDEOS_DIR / f"{video_id}.mp4"
        if not video.exists():
            missing.append(video_id)
            continue
        frames, aspect = tracked(video_id, video, fps, cap_s)
        rows += video_rows(video_id, frames, aspect)
        log.info("[%d/%d] %s (%s): %d rows", number, len(views), video_id, view, len(rows))
    if missing:
        log.error("%d videos missing (run fetch_youtube.py): %s", len(missing), ", ".join(missing))
        return 1
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(views)} videos ({sum(v == 'front' for v in views.values())} front, {sum(v == 'side' for v in views.values())} side)")
    print_counts(rows, len(views))
    return 0


def run_clips(clips: list[str], fps: float, cap_s: float) -> int:
    for clip in clips:
        path = Path(clip)
        frames, aspect = tracked(path.stem, path, fps, cap_s)
        analysis = judge(frames, aspect, path.stem)
        flags = [f"{f['rule']} {f['direction']} {f['start_s']:.1f}-{f['end_s']:.1f}s ({f['value']:.2f} vs {f['threshold']:.2f})" for f in analysis["flags"]]
        print(f"{path.name}: {analysis['view']}, baseline defaulted {analysis['baseline']['defaulted']}: {'; '.join(flags) or 'no flags'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--cap-s", type=float, default=DEFAULT_CAP_S, help="first N seconds of video; 0 for the whole video")
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE", help="override a config.py setting for this run")
    parser.add_argument("--clips", nargs="+", help="judge these videos and print their flags instead of the good set")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    apply_overrides(args.set)
    return run_clips(args.clips, args.fps, args.cap_s) if args.clips else run_good_set(args.fps, args.cap_s)


if __name__ == "__main__":
    sys.exit(main())
