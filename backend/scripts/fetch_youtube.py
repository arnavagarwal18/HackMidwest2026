"""Download the approved YouTube trumpet videos listed in testdata/youtube/videos.csv.

Usage (from the repo root): backend/.venv/Scripts/python backend/scripts/fetch_youtube.py [--limit N] [--only-group "Search group"]

Each video lands in testdata/youtube/videos/<youtube id>.mp4 (mp4, at most 720p, with audio). Files that already exist are
skipped, and a video that cannot be downloaded (private, removed, age-gated, region-blocked) is recorded as failed while the
rest carry on. testdata/youtube/manifest.csv is rewritten at the end with one row per video.
"""
import argparse
import csv
import logging
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import imageio_ffmpeg
import yt_dlp

YOUTUBE_DIR = Path(__file__).parents[2] / "testdata" / "youtube"
VIDEOS_CSV = YOUTUBE_DIR / "videos.csv"
MANIFEST_CSV = YOUTUBE_DIR / "manifest.csv"
VIDEOS_DIR = YOUTUBE_DIR / "videos"
MANIFEST_FIELDS = ["id", "title", "url", "search_group", "status", "duration_s", "width", "height", "file_size_mb"]
FORMAT = "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]"

log = logging.getLogger("fetch_youtube")


def video_id(url: str) -> str:
    """The YouTube video id of a watch / youtu.be URL; raises ValueError for any other URL."""
    parsed = urlparse(url)
    ids = parse_qs(parsed.query).get("v") or ([parsed.path.strip("/")] if parsed.netloc.endswith("youtu.be") else [])
    if not ids or not ids[0]:
        raise ValueError(f"cannot find a YouTube video id in {url!r}")
    return ids[0]


def read_rows(group: str | None, limit: int | None) -> list[dict]:
    with VIDEOS_CSV.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if group is not None:
        rows = [r for r in rows if r["Search group"] == group]
        if not rows:
            raise SystemExit(f"no rows in {VIDEOS_CSV.name} have Search group {group!r}")
    return rows[:limit]


def read_previous_manifest() -> dict[str, dict]:
    if not MANIFEST_CSV.exists():
        return {}
    with MANIFEST_CSV.open(encoding="utf-8", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def downloader() -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL({
        "format": FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(VIDEOS_DIR / "%(id)s.%(ext)s"),
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    })


def size_mb(path: Path) -> float | str:
    return round(path.stat().st_size / 1e6, 1) if path.exists() else ""


def manifest_row(row: dict, vid: str, status: str, info: dict | None = None, path: Path | None = None) -> dict:
    info = info or {}
    return {
        "id": vid, "title": row["Title"], "url": row["URL"], "search_group": row["Search group"], "status": status,
        "duration_s": info.get("duration", ""), "width": info.get("width", ""), "height": info.get("height", ""),
        "file_size_mb": size_mb(path) if path else "",
    }


def fetch_one(ydl: yt_dlp.YoutubeDL, row: dict, previous: dict[str, dict]) -> dict:
    url = row["URL"]
    try:
        vid = video_id(url)
    except ValueError as e:
        log.error("%s", e)
        return manifest_row(row, "", f"failed: {e}")
    path = VIDEOS_DIR / f"{vid}.mp4"
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
        return manifest_row(row, vid, f"failed: {reason}")
    return manifest_row(row, vid, "ok", info, path)


def write_manifest(rows: list[dict]) -> None:
    with MANIFEST_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, help="only the first N rows (after --only-group)")
    parser.add_argument("--only-group", help='only rows whose "Search group" is exactly this')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    rows = read_rows(args.only_group, args.limit)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    previous = read_previous_manifest()
    with downloader() as ydl:
        results = [fetch_one(ydl, row, previous) for row in rows]
    # keep manifest rows of earlier runs for videos not in this run, so a partial run never erases them
    this_run = {r["id"] for r in results}
    write_manifest(results + [r for i, r in previous.items() if i not in this_run])

    failed = [r for r in results if r["status"] != "ok"]
    log.info("%d of %d ok, %d failed; manifest: %s", len(results) - len(failed), len(results), len(failed), MANIFEST_CSV)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
