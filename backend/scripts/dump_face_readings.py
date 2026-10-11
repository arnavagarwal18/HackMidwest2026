"""Run the form pipeline with the face check on a video and dump the Face Landmarker's per-frame readings.

Usage (from backend/): .venv/Scripts/python scripts/dump_face_readings.py VIDEO CSV_OUT [--split-s SECONDS] [--cheek-width] [--max-seconds 290]

--cheek-width adds a cheek_width column: the distance between Face Mesh landmarks 234 and 454 (the cheeks' outer edges)
divided by the distance between landmarks 33 and 263 (the outer eye corners), in the face crop's pixels.

Frames are read with the whole video as one 'note' so every sampled frame has a reading; the form rules are then judged
on only the frames inside the notes transcribed from the video's audio, as the app does.

Only the first --max-seconds (default 290, the video-length cap of video_cap.py that bounds memory use; 0 lifts it, for deliberate
full-length runs on other machines) of the video are tracked; the audio is still transcribed whole.
"""
import argparse
import csv
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parent))  # for the sibling video_cap module

from app.form import config  # noqa: E402
from app.form import face  # noqa: E402
from app.form.face import FaceReader, FaceResult  # noqa: E402
from app.form.rules import analyse  # noqa: E402
from app.takes.media_tools import extract_wav  # noqa: E402
from app.takes.transcribe import transcribe  # noqa: E402
from video_cap import add_max_seconds_argument, analysis_window, track_video_capped  # noqa: E402


LEFT_CHEEK, RIGHT_CHEEK, LEFT_EYE_OUTER, RIGHT_EYE_OUTER = 234, 454, 33, 263  # Face Mesh landmark indices

WALL_LIMIT_S = 10_000  # track_video's own wall-clock limit: effectively none, the video-time cap decides
NO_CAP_WINDOW_S = 1e6  # the reader window when the video is not capped

cheek_widths: dict[float, float] = {}  # frame time -> cheek width / inter-eye distance, filled when --cheek-width is on


class _WidthRecordingLandmarker(face._MediaPipeFaceLandmarker):
    """The app's Face Landmarker that also keeps the cheek-width ratio of the last face it saw (None when no face)."""

    last_width: float | None = None

    def detect(self, rgb):
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=face.np.ascontiguousarray(rgb))
        result = self._landmarker.detect(image)
        self.last_width = None
        if not result.face_blendshapes:
            return None
        height, width = rgb.shape[:2]
        mesh = result.face_landmarks[0]

        def gap(a: int, b: int) -> float:
            return ((mesh[a].x - mesh[b].x) * width) ** 2 + ((mesh[a].y - mesh[b].y) * height) ** 2

        eyes = gap(LEFT_EYE_OUTER, RIGHT_EYE_OUTER)
        self.last_width = (gap(LEFT_CHEEK, RIGHT_CHEEK) / eyes) ** 0.5 if eyes else None
        return {shape.category_name: shape.score for shape in result.face_blendshapes[0]}


class _WidthRecordingReader(FaceReader):
    def read(self, bgr, seconds, frame):
        super().read(bgr, seconds, frame)
        landmarker = self._landmarker
        if landmarker is not None and seconds in self.result.readings:
            width = landmarker.last_width
            if width is not None:
                cheek_widths[seconds] = width


def read_frames(video: Path, view: str | None, limit_s: float, with_width: bool = False):
    """(tracked, face result) for the first limit_s seconds of video."""
    cheek_widths.clear()
    reader_class = _WidthRecordingReader if with_width else FaceReader
    if with_width:
        face._create_landmarker = _WidthRecordingLandmarker
    with reader_class([{"onset_s": 0.0, "offset_s": limit_s}], view) as reader:
        tracked = track_video_capped(video, limit_s, WALL_LIMIT_S, on_frame=reader.read)
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


def print_cheek_puff_summary(result: FaceResult) -> None:
    print(summary("all frames", list(result.readings.values())))


def print_cheek_width_summary() -> None:
    widths = list(cheek_widths.values())
    if widths:
        print(f"cheek_width: n={len(widths)} min={min(widths):.3f} median={statistics.median(widths):.3f} "
              f"p90={percentile(widths, 0.9):.3f} max={max(widths):.3f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("csv_out", type=Path)
    parser.add_argument("--split-s", type=float, help="where the owner says the behaviour changes (adds the half-by-half summary)")
    parser.add_argument("--cheek-width", action="store_true", help="add the landmark-based cheek_width column")
    add_max_seconds_argument(parser)
    args = parser.parse_args()
    window_s = analysis_window(NO_CAP_WINDOW_S, args.max_seconds)  # seconds of video tracked and read

    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / "audio.wav"
        extract_wav(args.video, wav)
        notes = [{"onset_s": n.onset_s, "offset_s": n.offset_s} for n in transcribe(wav, "trumpet")]
    print(f"notes transcribed: {len(notes)}, first {notes[0]['onset_s']:.2f}s, last end {notes[-1]['offset_s']:.2f}s")

    tracked, everywhere = read_frames(args.video, None, window_s, args.cheek_width)
    analysis = analyse(tracked.frames, "trumpet", "t1", tracked.width, tracked.height, everywhere)
    if analysis["view"] == "side":
        tracked, everywhere = read_frames(args.video, "side", window_s, args.cheek_width)
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
        writer.writerow(["t", "in_note", "cheekPuff", "smile"] + (["cheek_width"] if args.cheek_width else []))
        for t, r in sorted(everywhere.readings.items()):
            writer.writerow([t, int(inside(t)), "" if r is None else round(r.cheek_puff, 4), "" if r is None else round(r.smile, 4)]
                        + ([round(cheek_widths[t], 4) if t in cheek_widths else ""] if args.cheek_width else []))
    if args.cheek_width:
        print_cheek_width_summary()
    if args.split_s is None:
        print_cheek_puff_summary(everywhere)
        return
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
