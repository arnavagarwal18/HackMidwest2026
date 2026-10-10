"""Run one recording through a running server and print how it was judged.

    python scripts/e2e_take.py testdata/take.wav --piece twinkle --bars 1-4 --bpm 90 [--downbeat 1.0]

Creates a session, picks and confirms the built-in piece, uploads the file as a take, waits for the
analysis, and prints the alignment quality, the number of problems and the tier 1 sentences.
Without --downbeat the file is sent as an upload (the grid is fitted to the notes it contains).
"""
import argparse
import sys
import time
from pathlib import Path

import httpx

DEFAULT_SERVER = "http://127.0.0.1:8000"
TIMEOUT_S = 180
POLL_S = 1.0
SETTLED = ("done", "failed")
CONTENT_TYPES = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg",
                 ".mp4": "video/mp4", ".mov": "video/quicktime"}


class E2EError(Exception):
    """A step against the server failed; the message says which and why."""


def parse_bars(text: str) -> tuple[int, int]:
    try:
        first, last = (int(part) for part in text.split("-"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"--bars must look like 1-4, got '{text}'")
    return first, last


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", type=Path, help="recording: .wav, .webm, .ogg, .mp4 or .mov")
    parser.add_argument("--piece", default="twinkle", help="built-in piece id (default twinkle)")
    parser.add_argument("--instrument", default="violin", choices=["violin", "trumpet"])
    parser.add_argument("--bars", type=parse_bars, default=(1, 4), help="bar range such as 1-4 (default 1-4)")
    parser.add_argument("--bpm", type=float, help="tempo the piece was played at (default: the score's tempo)")
    parser.add_argument("--downbeat", type=float, help="seconds into the file where the first beat sounds")
    parser.add_argument("--server", default=DEFAULT_SERVER)
    return parser.parse_args(argv)


def check(response: httpx.Response, step: str) -> dict:
    if response.status_code >= 400:
        raise E2EError(f"{step} failed: HTTP {response.status_code} {response.text}")
    return response.json()


def prepare_session(http: httpx.Client, instrument: str, piece: str) -> tuple[str, float]:
    """Create a session with the piece confirmed; returns (session_id, the score's tempo in BPM)."""
    session_id = check(http.post("/sessions", json={"instrument": instrument}), "Creating the session")["session_id"]
    check(http.post(f"/sessions/{session_id}/score/file", json={"builtin": piece}), f"Picking the piece '{piece}'")
    confirmed = check(http.post(f"/sessions/{session_id}/score/confirm"), "Confirming the score")
    return session_id, confirmed["tempo_bpm"]


def upload_take(http: httpx.Client, session_id: str, args: argparse.Namespace, bpm: float) -> str:
    content_type = CONTENT_TYPES.get(args.audio.suffix.lower())
    if content_type is None:
        raise E2EError(f"Unsupported file type '{args.audio.suffix}'. Use one of: {', '.join(CONTENT_TYPES)}.")
    form = {"kind": "video" if content_type.startswith("video/") else "mic",
            "source": "recorded" if args.downbeat is not None else "uploaded",
            "bar_from": args.bars[0], "bar_to": args.bars[1], "tempo_bpm": bpm, "count_in_beats": 0}
    if args.downbeat is not None:
        form["downbeat_s"] = args.downbeat
    response = http.post(f"/sessions/{session_id}/takes", data={k: str(v) for k, v in form.items()},
                         files={"file": (args.audio.name, args.audio.read_bytes(), content_type)})
    return check(response, "Uploading the take")["take_id"]


def wait_for_analysis(http: httpx.Client, session_id: str, take_id: str) -> dict:
    deadline = time.monotonic() + TIMEOUT_S
    while time.monotonic() < deadline:
        analysis = check(http.get(f"/sessions/{session_id}/takes/{take_id}/analysis"), "Reading the analysis")
        if analysis["status"] in SETTLED:
            return analysis
        time.sleep(POLL_S)
    raise E2EError(f"The take was still '{analysis['status']}' after {TIMEOUT_S} s.")


def print_report(analysis: dict) -> None:
    if analysis["status"] == "failed":
        raise E2EError(f"The take failed: {analysis['error']}")
    print(f"status:            {analysis['status']}")
    print(f"alignment quality: {analysis['alignment_quality']}")
    print(f"can't tell:        {analysis['cant_tell']} {analysis['cant_tell_reason'] or ''}".rstrip())
    print(f"tempo:             {analysis['tempo']}")
    print(f"problems:          {len(analysis['problems'])}")
    for sentence in analysis["tier1"]:
        print(f"  - {sentence['text']}")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not args.audio.is_file():
        print(f"Can't find the recording {args.audio}.", file=sys.stderr)
        return 2
    try:
        with httpx.Client(base_url=args.server, timeout=60) as http:
            session_id, score_bpm = prepare_session(http, args.instrument, args.piece)
            take_id = upload_take(http, session_id, args, args.bpm or score_bpm)
            print_report(wait_for_analysis(http, session_id, take_id))
    except (E2EError, httpx.HTTPError) as error:
        print(f"e2e_take: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
