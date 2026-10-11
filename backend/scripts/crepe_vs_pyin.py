"""Compare the pYIN and CREPE transcribers on the demo videos: speed and how well the notes line up with the score.

    .venv/bin/python scripts/crepe_vs_pyin.py [--capacities tiny,full] [--output scripts/crepe_vs_pyin_results.md]

Needs the optional CREPE install (`pip install crepe tensorflow`). Each video goes through the pipeline's own steps (audio
extraction, calibration from the video, transcription, the diagnosis line-up) in this process, with AI off and no server.
Scanning a sheet photo runs homr once per photo (about a minute); the scan is cached for the rest of the run.
"""
import argparse
import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("AI_ENABLED", "false")

import librosa  # noqa: E402

from app.diagnosis import config as diagnosis_config  # noqa: E402
from app.diagnosis.transposition import align_with_transposition  # noqa: E402
from app.score import clean, homr_runner  # noqa: E402
from app.score.ingest import ingest_musicxml_file  # noqa: E402
from app.takes import transcribe as pyin  # noqa: E402
from app.takes.crepe_pitch import CAPACITIES, CREPE_CAPACITY_ENV, transcribe_crepe  # noqa: E402
from app.takes.media_tools import extract_wav  # noqa: E402
from app.takes.transcribe import DEFAULT_PROFILE, SAMPLE_RATE  # noqa: E402
from app.takes.video_calibration import SEARCH_WINDOW_S, calibrate_from_audio  # noqa: E402

logger = logging.getLogger("crepe_vs_pyin")

INSTRUMENT = "trumpet"
SPOT_CHECK_NOTES = 20
TIME_TARGET_S = 15.0
AUDIO_TARGET_S = 30.0
PHOTO_SUFFIXES = (".webp", ".jpg", ".jpeg", ".png")
TESTDATA = REPO / "testdata"


@dataclass
class Job:
    name: str
    score: Path  # a sheet photo or a MusicXML file
    video: Path
    bars: tuple[int, int]
    bpm: float | None = None  # None: the scanned score's tempo


JOBS = [
    Job("video1", TESTDATA / "trumpet_video1_sheet.webp", TESTDATA / "trumpet_video1.mp4", (1, 16)),
    Job("video2", TESTDATA / "trumpet_video2_sheet.webp", TESTDATA / "trumpet_video2.mp4", (1, 20)),
    Job("ode_to_joy", TESTDATA / "ode_to_joy" / "score.musicxml", TESTDATA / "ode_to_joy" / "ode_to_joy_trumpet11.mp4",
        (1, 16), 100.0),
]


def load_score(job: Job, work: Path) -> dict:
    """The job's score as the diagnosis reads it; a photo is scanned with homr (no AI reader), as with AI off in the app."""
    folder = work / job.name
    folder.mkdir(exist_ok=True)
    if job.score.suffix.lower() in PHOTO_SUFFIXES:
        score = homr_runner.run_homr(clean.clean_photo(job.score, folder / clean.CLEANED_FILENAME), folder)
    else:
        score = ingest_musicxml_file(folder, job.score)
    return json.loads(score.to_json())


def transcribers(capacities: list[str]) -> dict:
    """name -> function(wav, instrument, profile, calib_end_s) for pYIN and each CREPE model size."""
    def crepe_with(capacity):
        def run(wav, instrument, profile, calib_end_s):
            os.environ[CREPE_CAPACITY_ENV] = capacity
            return transcribe_crepe(wav, instrument, {**DEFAULT_PROFILE, **(profile or {})}, calib_end_s)
        return run
    return {"pyin": pyin.transcribe, **{f"crepe-{capacity}": crepe_with(capacity) for capacity in capacities}}


def measure(run, wav: Path, profile, calib_end_s: float, duration_s: float) -> tuple[list[dict], float]:
    """(notes, seconds the transcription took per 30 s of audio)."""
    start = time.monotonic()
    notes = [note.to_dict() for note in run(wav, INSTRUMENT, profile, calib_end_s)]
    return notes, (time.monotonic() - start) * AUDIO_TARGET_S / duration_s


def line_up(job: Job, score: dict, notes: list[dict]) -> dict:
    """Matched (ok + wrong), missed and extra notes against the score, and how many of the first 20 expected notes are ok."""
    take = {"take_id": job.name, "bar_from": job.bars[0], "bar_to": job.bars[1], "tempo_bpm": job.bpm or score["tempo_bpm"]}
    _, aligned = align_with_transposition(score, notes, take, INSTRUMENT, None)
    statuses = [note["status"] for note in aligned["notes"]]
    return {
        "played": len(notes),
        "expected": len(statuses),
        "ok": statuses.count(diagnosis_config.STATUS_OK),
        "wrong": statuses.count(diagnosis_config.STATUS_WRONG),
        "missed": statuses.count(diagnosis_config.STATUS_MISSED),
        "extra": len(aligned["extras"]),
        "spot_ok": statuses[:SPOT_CHECK_NOTES].count(diagnosis_config.STATUS_OK),
        "quality": aligned["alignment_quality"],
    }


def warm_up_crepe(capacities: list[str]) -> float:
    """Import TensorFlow and load each model once so the timed runs don't pay for it; returns the seconds that took."""
    import numpy as np
    start = time.monotonic()
    silence = np.zeros(SAMPLE_RATE, dtype="float32")
    for capacity in capacities:
        from app.takes.crepe_pitch import frame_pitches_crepe
        frame_pitches_crepe(silence, INSTRUMENT, DEFAULT_PROFILE, capacity)
    return time.monotonic() - start


def run_job(job: Job, work: Path, runs: dict) -> list[dict]:
    score = load_score(job, work)
    wav = work / f"{job.name}.wav"
    extract_wav(job.video, wav)
    audio, _ = librosa.load(str(wav), sr=SAMPLE_RATE, mono=True)
    duration_s = len(audio) / SAMPLE_RATE
    profile, calib_end_s = calibrate_from_audio(audio[: int(SEARCH_WINDOW_S * SAMPLE_RATE)], INSTRUMENT)
    rows = []
    for name, run in runs.items():
        notes, seconds_per_30s = measure(run, wav, profile, calib_end_s, duration_s)
        rows.append({"video": job.name, "transcriber": name, "audio_s": duration_s, "s_per_30s": seconds_per_30s,
                     **line_up(job, score, notes)})
        logger.info("%s", rows[-1])
    return rows


def format_table(rows: list[dict]) -> str:
    head = ("| Video | Transcriber | Audio s | Seconds per 30 s of audio | Under 15 s? | Played | Expected | Matched (ok + wrong) | "
            "ok | wrong | Missed | Extra | First 20 expected ok | Alignment |\n|" + "---|" * 14)
    lines = [
        f"| {r['video']} | {r['transcriber']} | {r['audio_s']:.1f} | {r['s_per_30s']:.1f} | "
        f"{'yes' if r['s_per_30s'] < TIME_TARGET_S else 'no'} | {r['played']} | {r['expected']} | {r['ok'] + r['wrong']} | "
        f"{r['ok']} | {r['wrong']} | {r['missed']} | {r['extra']} | {r['spot_ok']}/{SPOT_CHECK_NOTES} | {r['quality']:.3f} |"
        for r in rows
    ]
    return "\n".join([head, *lines])


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--capacities", default="tiny,full", help=f"CREPE model sizes to run, from {','.join(CAPACITIES)}")
    parser.add_argument("--output", type=Path, default=BACKEND / "scripts" / "crepe_vs_pyin_results.md")
    parser.add_argument("--only", help="run just this video (video1, video2 or ode_to_joy)")
    args = parser.parse_args(argv)
    args.capacities = [c.strip() for c in args.capacities.split(",") if c.strip()]
    unknown = [c for c in args.capacities if c not in CAPACITIES]
    if unknown:
        parser.error(f"unknown CREPE capacities {unknown}; use {','.join(CAPACITIES)}")
    return args


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args(argv)
    jobs = [job for job in JOBS if args.only in (None, job.name)]
    missing = [path for job in jobs for path in (job.score, job.video) if not path.is_file()]
    if missing:
        print(f"Can't find {', '.join(str(p) for p in missing)}.", file=sys.stderr)
        return 2
    try:
        warmup_s = warm_up_crepe(args.capacities)
    except ImportError as error:
        print(f"CREPE is not installed ({error}); run `pip install crepe tensorflow` in the venv.", file=sys.stderr)
        return 2
    rows = []
    with tempfile.TemporaryDirectory(prefix="crepe_vs_pyin_") as work:
        for job in jobs:
            rows += run_job(job, Path(work), transcribers(args.capacities))
    table = format_table(rows)
    args.output.write_text(
        f"# CREPE vs pYIN (trumpet)\n\nGenerated by `backend/scripts/crepe_vs_pyin.py`. First-time TensorFlow import and model "
        f"load, not counted in the times: {warmup_s:.1f} s.\n\n{table}\n", encoding="utf-8")
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
