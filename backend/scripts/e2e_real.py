"""Run a real sheet photo (or a MusicXML score) and a real video take through a running server, timing every step.

    python scripts/e2e_real.py ../testdata/trumpet_video1_sheet.webp ../testdata/trumpet_video1.mp4 [--bars 1-8] [--bpm 80]
    python scripts/e2e_real.py ../testdata/hot_cross_buns/score.musicxml take.mp4 [--bars 1-4] [--bpm 100]

Follows the browser's route sequence: session, photo scan (a .xml/.musicxml/.mxl score is uploaded as a score file instead), confirm, video take, analysis, feedback, tracks,
score status. Prints the HTTP status and seconds of each step, then the facts worth judging.
"""
import argparse
import collections
import json
import sys
import time
from pathlib import Path

import httpx

DEFAULT_SERVER = "http://127.0.0.1:8000"
SCAN_TIMEOUT_S = 300
TAKE_TIMEOUT_S = 600
POLL_S = 1.0
PHOTO_TYPES = {".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
SCORE_FILE_TYPES = {".xml": "application/xml", ".musicxml": "application/vnd.recordare.musicxml+xml",
                    ".mxl": "application/vnd.recordare.musicxml"}
VIDEO_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}


class E2EError(Exception):
    """A step against the server failed; the message says which and why."""


class Steps:
    """Runs each step, printing its HTTP status and duration."""

    def run(self, name: str, call) -> httpx.Response:
        start = time.monotonic()
        response = call()
        print(f"[{response.status_code}] {name}: {time.monotonic() - start:.1f} s", flush=True)
        if response.status_code >= 400:
            raise E2EError(f"{name} failed: HTTP {response.status_code} {response.text[:500]}")
        return response

    def poll(self, name: str, call, settled, timeout_s: float) -> dict:
        start = time.monotonic()
        polls, body = 0, {}
        while time.monotonic() - start < timeout_s:
            response = call()
            polls += 1
            if response.status_code >= 400:
                raise E2EError(f"{name} failed: HTTP {response.status_code} {response.text[:500]}")
            body = response.json()
            if settled(body):
                print(f"[{response.status_code}] {name}: {time.monotonic() - start:.1f} s ({polls} polls)", flush=True)
                return body
            time.sleep(POLL_S)
        raise E2EError(f"{name} still not settled after {timeout_s} s: {json.dumps(body)[:300]}")


def parse_bars(text: str) -> tuple[int, int]:
    try:
        first, last = (int(part) for part in text.split("-"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--bars must look like 1-8, got '{text}'")
    return first, last


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("photo", type=Path)
    parser.add_argument("video", type=Path)
    parser.add_argument("--instrument", default="trumpet", choices=["violin", "trumpet"])
    parser.add_argument("--bars", type=parse_bars, help="bar range such as 1-8 (default: the first 8 scanned bars)")
    parser.add_argument("--bpm", type=float, help="tempo (default: the scanned score's tempo)")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    return parser.parse_args(argv)


def content_type(path: Path, allowed: dict[str, str]) -> str:
    kind = allowed.get(path.suffix.lower())
    if kind is None:
        raise E2EError(f"Unsupported file type '{path.suffix}'. Use one of: {', '.join(allowed)}.")
    return kind


def scan_photo(http: httpx.Client, steps: Steps, session_id: str, photo: Path) -> dict:
    steps.run("upload photo", lambda: http.post(
        f"/sessions/{session_id}/score/photo",
        files={"file": (photo.name, photo.read_bytes(), content_type(photo, PHOTO_TYPES))}))
    status = steps.poll("scan", lambda: http.get(f"/sessions/{session_id}/score/status"),
                        lambda body: body["score_status"] != "scanning", SCAN_TIMEOUT_S)
    print("scan status:", json.dumps(status))
    if status["score_status"] != "scanned":
        raise E2EError(f"The scan ended as '{status['score_status']}': {status['score_error']}")
    return status


def upload_score_file(http: httpx.Client, steps: Steps, session_id: str, score: Path) -> None:
    steps.run("upload score file", lambda: http.post(
        f"/sessions/{session_id}/score/file",
        files={"file": (score.name, score.read_bytes(), content_type(score, SCORE_FILE_TYPES))}))


def upload_take(http: httpx.Client, steps: Steps, session_id: str, args: argparse.Namespace, confirmed: dict) -> str:
    first, last = args.bars or (1, min(confirmed["bars"], 8))
    form = {"kind": "video", "source": "uploaded", "bar_from": first, "bar_to": last,
            "tempo_bpm": args.bpm or confirmed["tempo_bpm"], "count_in_beats": 0}
    print("take form:", form)
    response = steps.run("upload take", lambda: http.post(
        f"/sessions/{session_id}/takes", data={k: str(v) for k, v in form.items()},
        files={"file": (args.video.name, args.video.read_bytes(), content_type(args.video, VIDEO_TYPES))}))
    return response.json()["take_id"]


def report(analysis: dict, tracks: dict) -> None:
    print("\n--- take ---")
    for key in ("status", "error", "alignment_quality", "cant_tell", "cant_tell_reason", "form_status", "tempo"):
        print(f"{key}: {analysis[key]}")
    counts = collections.Counter(note["status"] for note in analysis["notes"])
    print("notes by status:", dict(counts), "| extras:", len(analysis["extras"]), "| problems:", len(analysis["problems"]))
    print("form flags:", json.dumps(analysis["form"]))
    print("tracks keys:", sorted(tracks), "| tracking_quality:", tracks.get("tracking_quality"))
    print("tier1:")
    for sentence in analysis["tier1"]:
        print(f"  - {sentence['text']}")


def run_flow(http: httpx.Client, steps: Steps, args: argparse.Namespace) -> None:
    session_id = steps.run("create session", lambda: http.post("/sessions", json={"instrument": args.instrument})).json()["session_id"]
    if args.photo.suffix.lower() in SCORE_FILE_TYPES:
        upload_score_file(http, steps, session_id, args.photo)
    else:
        scan_photo(http, steps, session_id, args.photo)
    confirmed = steps.run("confirm score", lambda: http.post(f"/sessions/{session_id}/score/confirm")).json()
    print("confirmed:", json.dumps(confirmed))
    take_id = upload_take(http, steps, session_id, args, confirmed)
    analysis = steps.poll("take analysis", lambda: http.get(f"/sessions/{session_id}/takes/{take_id}/analysis"),
                          lambda body: body["status"] in ("done", "failed"), TAKE_TIMEOUT_S)
    analysis = steps.poll("form analysis", lambda: http.get(f"/sessions/{session_id}/takes/{take_id}/analysis"),
                          lambda body: body["form_status"] not in ("processing", "queued"), TAKE_TIMEOUT_S)
    feedback = steps.run("get feedback", lambda: http.get(f"/sessions/{session_id}/takes/{take_id}/feedback")).json()
    tracks = {}
    if analysis["form_status"] == "done":
        tracks = steps.run("get tracks", lambda: http.get(f"/sessions/{session_id}/takes/{take_id}/tracks")).json()
    final_status = steps.run("score status", lambda: http.get(f"/sessions/{session_id}/score/status")).json()
    report(analysis, tracks)
    print("\n--- feedback ---\n" + json.dumps(feedback, indent=1)[:3000])
    print("\n--- final score status ---\n" + json.dumps(final_status))


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    for path in (args.photo, args.video):
        if not path.is_file():
            print(f"Can't find {path}.", file=sys.stderr)
            return 2
    try:
        with httpx.Client(base_url=args.server, timeout=120) as http:
            run_flow(http, Steps(), args)
    except (E2EError, httpx.HTTPError) as error:
        print(f"e2e_real: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
