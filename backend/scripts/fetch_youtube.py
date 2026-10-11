"""Download the YouTube trumpet videos listed in testdata/youtube/videos.csv (good posture) or fault_candidates.csv.

Usage (from the repo root): backend/.venv/Scripts/python backend/scripts/fetch_youtube.py [--list PATH] [--limit N] [--only-group "Search group"]

Good-posture list (default): each video lands in testdata/youtube/videos/<youtube id>.mp4 and testdata/youtube/manifest.csv
records them. With --list testdata/youtube/fault_candidates.csv they land in testdata/youtube/fault_videos/ with
fault_manifest.csv, and --only-group matches the sheet's "Scenario" column. Videos are mp4, at most 720p, with audio. Files
that already exist are skipped, and a video that cannot be downloaded (private, removed, age-gated, region-blocked) is recorded
as failed while the rest carry on. The manifest is rewritten at the end with one row per video.
"""
import argparse
import csv
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp

YOUTUBE_DIR = Path(__file__).parents[2] / "testdata" / "youtube"
FAULT_CSV = YOUTUBE_DIR / "fault_candidates.csv"
MANIFEST_FIELDS = ["id", "title", "url", "search_group", "status", "duration_s", "width", "height", "file_size_mb"]
FORMAT = "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]"

log = logging.getLogger("fetch_youtube")


@dataclass(frozen=True)
class VideoList:
    """One list of videos: its CSV, the column that groups its rows, and where its downloads and manifest go."""
    csv_path: Path
    group_column: str
    videos_dir: Path
    manifest_path: Path


GOOD_LIST = VideoList(YOUTUBE_DIR / "videos.csv", "Search group", YOUTUBE_DIR / "videos", YOUTUBE_DIR / "manifest.csv")
FAULT_LIST = VideoList(FAULT_CSV, "Scenario", YOUTUBE_DIR / "fault_videos", YOUTUBE_DIR / "fault_manifest.csv")


def pick_list(csv_arg: str | None) -> VideoList:
    """The list to fetch: the good-posture list by default, the fault list for fault_candidates.csv, else an error."""
    if csv_arg is None:
        return GOOD_LIST
    for video_list in (GOOD_LIST, FAULT_LIST):
        if Path(csv_arg).resolve() == video_list.csv_path.resolve():
            return video_list
    raise SystemExit(f"unknown --list {csv_arg!r}; use {GOOD_LIST.csv_path} or {FAULT_LIST.csv_path}")


def video_id(url: str) -> str:
    """The YouTube video id of a watch / youtu.be URL; raises ValueError for any other URL."""
    parsed = urlparse(url)
    ids = parse_qs(parsed.query).get("v") or ([parsed.path.strip("/")] if parsed.netloc.endswith("youtu.be") else [])
    if not ids or not ids[0]:
        raise ValueError(f"cannot find a YouTube video id in {url!r}")
    return ids[0]


def read_rows(video_list: VideoList, group: str | None, limit: int | None) -> list[dict]:
    with video_list.csv_path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if group is not None:
        rows = [r for r in rows if r[video_list.group_column] == group]
        if not rows:
            raise SystemExit(f"no rows in {video_list.csv_path.name} have {video_list.group_column} {group!r}")
    return rows[:limit]


def read_previous_manifest(video_list: VideoList) -> dict[str, dict]:
    if not video_list.manifest_path.exists():
        return {}
    with video_list.manifest_path.open(encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def downloader(videos_dir: Path) -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL({
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(videos_dir / "%(id)s.%(ext)s"),
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    })


def size_mb(path: Path) -> float | str:
    return round(path.stat().st_size / 1e6, 1) if path.exists() else ""


def manifest_row(video_list: VideoList, row: dict, vid: str, status: str, info: dict | None = None,
                 path: Path | None = None) -> dict:
    info = info or {}
    return {
        "id": vid, "title": row["Title"], "url": row["URL"], "search_group": row[video_list.group_column], "status": status,
        "duration_s": info.get("duration", ""), "width": info.get("width", ""), "height": info.get("height", ""),
        "file_size_mb": size_mb(path) if path else "",
    }


def fetch_one(ydl: yt_dlp.YoutubeDL, video_list: VideoList, row: dict, previous: dict[str, dict]) -> dict:
    url = row["URL"]
    try:
        vid = video_id(url)
    except ValueError as e:
        log.error("%s", e)
        return manifest_row(video_list, row, "", f"failed: {e}")
    path = video_list.videos_dir / f"{vid}.mp4"
    try:
        if path.exists():
            log.info("%s already downloaded, skipping", vid)
            if previous.get(vid, {}).get("status") == "ok":
                return {**previous[vid], "file_size_mb": size_mb(path)}
            info = ydl.extract_info(url, download=False)  # no earlier manifest row: look the details up
        else:
            log.info("downloading %s (%s)", vid, row["Title"][:60])
            info = ydl.extract_info(url, download=True)
    except Exception as e:  # yt-dlp raises many error types; every one becomes a failed row carrying its reason
        reason = " ".join(str(e).replace("ERROR:", "").split())
        log.error("%s failed: %s", vid, reason)
        return manifest_row(video_list, row, vid, f"failed: {reason}")
    return manifest_row(video_list, row, vid, "ok", info, path)


def write_manifest(video_list: VideoList, rows: list[dict]) -> None:
    with video_list.manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", dest="list_csv", help=f"CSV to fetch: {GOOD_LIST.csv_path.name} (default) or {FAULT_CSV.name}")
    parser.add_argument("--limit", type=int, help="only the first N rows (after --only-group)")
    parser.add_argument("--only-group", help='only rows whose "Search group" (fault list: "Scenario") is exactly this')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    video_list = pick_list(args.list_csv)
    rows = read_rows(video_list, args.only_group, args.limit)
    video_list.videos_dir.mkdir(parents=True, exist_ok=True)
    previous = read_previous_manifest(video_list)
    with downloader(video_list.videos_dir) as ydl:
        results = [fetch_one(ydl, video_list, row, previous) for row in rows]
    # keep manifest rows of earlier runs for videos not in this run, so a partial run never erases them
    this_run = {r["id"] for r in results}
    write_manifest(video_list, results + [r for i, r in previous.items() if i not in this_run])

    failed = [r for r in results if r["status"] != "ok"]
    log.info("%d of %d ok, %d failed; manifest: %s", len(results) - len(failed), len(results), len(failed), video_list.manifest_path)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
