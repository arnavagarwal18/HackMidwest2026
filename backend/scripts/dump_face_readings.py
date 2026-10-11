"""Run the form pipeline with the face check on a video and dump the Face Landmarker's per-frame readings.

Usage (from backend/): .venv/Scripts/python scripts/dump_face_readings.py VIDEO CSV_OUT [--split-s SECONDS]

Frames are read with the whole video as one 'note' so every sampled frame has a reading; the form rules are then judged
on only the frames inside the notes transcribed from the video's audio, as the app does.
"""
import argparse
import csv
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.form import config  # noqa: E402
from app.form.face import FaceReader, FaceResult  # noqa: E402
from app.form.rules import analyse  # noqa: E402
from app.form.track import track_video  # noqa: E402
from app.takes.media_tools import extract_wav  # noqa: E402
from app.takes.transcribe import transcribe  # noqa: E402


def read_frames(video: Path, view: str | None, duration_s: float):
    with FaceReader([{"onset_s": 0.0, "offset_s": duration_s}], view) as reader:
        tracked = track_video(video, with_hands=False, time_limit_s=10_000, on_frame=reader.read)
    return tracked, reader.result


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def summary(label: str, readings: list) -> str:
    found = [r for r in readings if r is not None]
    if not found:
        return f"{label}: no face readings"
    puff, smile = [r.cheek_puff for r in found], [r.smile for r in found]
    return (f"{label}: n={len(found)}/{len(readings)} cheekPuff median={statistics.median(puff):.3f} p90={percentile(puff, 0.9):.3f} "
            f"max={max(puff):.3f} | smile median={statistics.median(smile):.3f} p90={percentile(smile, 0.9):.3f} max={max(smile):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("csv_out", type=Path)
    parser.add_argument("--split-s", type=float, required=True, help="where the owner says the behaviour changes")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / "audio.wav"
        extract_wav(args.video, wav)
        notes = [{"onset_s": n.onset_s, "offset_s": n.offset_s} for n in transcribe(wav, "trumpet")]
    print(f"notes transcribed: {len(notes)}, first {notes[0]['onset_s']:.2f}s, last end {notes[-1]['offset_s']:.2f}s")

    tracked, everywhere = read_frames(args.video, None, 1e6)
    analysis = analyse(tracked.frames, "trumpet", "t1", tracked.width, tracked.height, everywhere)
    if analysis["view"] == "side":
        tracked, everywhere = read_frames(args.video, "side", 1e6)
    in_notes = FaceResult(readings={t: r for t, r in everywhere.readings.items() if any(a <= t < b for a, b in map(lambda n: (n["onset_s"], n["offset_s"]), notes))})
    final = analyse(tracked.frames, "trumpet", "t1", tracked.width, tracked.height, in_notes)
    print(f"view={final['view']} view_ratio={final['view_ratio']} face_quality(in notes)={in_notes.face_quality} "
          f"face_quality(all frames)={everywhere.face_quality} rules_skipped={final['rules_skipped']}")
    print("flags:")
    for flag in final["flags"]:
        print(f"  {flag['rule']} {flag['start_s']:.1f}-{flag['end_s']:.1f}s severity={flag.get('severity')}")

    def inside(t: float) -> bool:
        return any(n["onset_s"] <= t < n["offset_s"] for n in notes)

    with args.csv_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["t", "in_note", "cheekPuff", "smile"])
        for t, r in sorted(everywhere.readings.items()):
            writer.writerow([t, int(inside(t)), "" if r is None else round(r.cheek_puff, 4), "" if r is None else round(r.smile, 4)])
    first = [r for t, r in everywhere.readings.items() if t < args.split_s]
    second = [r for t, r in everywhere.readings.items() if t >= args.split_s]
    print(summary(f"all frames, first half (<{args.split_s}s)", first))
    print(summary("all frames, second half", second))
    first_n = [r for t, r in in_notes.readings.items() if t < args.split_s]
    second_n = [r for t, r in in_notes.readings.items() if t >= args.split_s]
    print(summary("in-note frames, first half", first_n))
    print(summary("in-note frames, second half", second_n))


if __name__ == "__main__":
    main()
