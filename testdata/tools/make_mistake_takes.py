"""Make the mistake takes in testdata/mistakes/ from the trumpet recordings in testdata/.

    backend/.venv/bin/python testdata/tools/make_mistake_takes.py [--only ode_to_joy] [--out testdata/mistakes]

For every source recording it writes two takes next to each other, in testdata/mistakes/<source>/:
  <source>_wrong_note.mp4          two notes pitch-shifted by one semitone, only over each note's own time span
  <source>_missed_and_rushing.mp4  one note silenced (the player skipped it), and one 4-bar phrase played 15% faster
                                   (time-stretch, pitch kept; the video is sped up by the same amount so it stays in sync)
Everything else is the original recording, re-encoded to 720p so each file stays under 10 MB.
Every edited note has a different pitch from both neighbours after the edit (the transcriber can't split same-pitch pairs).
The note times below are the app's own transcription of the originals (see ANSWER_KEY.md); the answer key lists what changed.
"""
import argparse
import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import librosa
import numpy as np
import soundfile

logger = logging.getLogger("make_mistake_takes")

TESTDATA = Path(__file__).resolve().parents[1]
NOTE_MARGIN_S = 0.02  # the edit covers the note's span plus this much each side (the gaps between notes are 40 ms or more)
FADE_S = 0.01
SHIFT_CONTEXT_S = 0.15  # audio around a note given to the pitch shifter, then thrown away
RUSH_RATE = 1.15
MAX_BYTES = 10 * 1000 * 1000
TARGET_BYTES = 9_500_000
CRF_STEPS = (26, 28, 30, 32, 34)
VIDEO_HEIGHT = 720
AUDIO_KBPS = 128


class MakeTakesError(Exception):
    """A take couldn't be made; the message says which step failed and why."""


@dataclass(frozen=True)
class NoteEdit:
    bar: int
    beat: float  # 1-based beat in the bar; 3.5 is the 'and' of beat 3
    name: str  # sounding (concert) pitch of the original note
    onset_s: float
    offset_s: float
    semitones: int = 0  # wrong notes only
    tail_s: float = NOTE_MARGIN_S  # how far past offset_s the edit reaches (a note's release can ring on after the transcribed end)


@dataclass(frozen=True)
class Phrase:
    bars: tuple[int, int]
    start_s: float  # both ends sit in the silence between notes
    end_s: float


@dataclass(frozen=True)
class Source:
    name: str
    video: Path
    wrong_notes: tuple[NoteEdit, NoteEdit]
    missed_note: NoteEdit
    rushed: Phrase


SOURCES = (
    Source("ode_to_joy", TESTDATA / "ode_to_joy" / "ode_to_joy_trumpet11.mp4",
           wrong_notes=(NoteEdit(3, 3, "A4", 8.21, 8.71, -1), NoteEdit(14, 2, "C5", 34.03, 34.49, +1)),
           missed_note=NoteEdit(11, 3, "B4", 27.38, 27.79, tail_s=0.17),
           rushed=Phrase((5, 8), 11.5, 21.1)),
    Source("trumpet_video1", TESTDATA / "trumpet_video1.mp4",
           wrong_notes=(NoteEdit(3, 3.5, "A4", 11.31, 11.67, -1), NoteEdit(13, 3.5, "G5", 48.79, 49.89, +1)),
           missed_note=NoteEdit(14, 2.5, "D5", 51.78, 52.20),
           rushed=Phrase((5, 8), 16.33, 31.1)),
    Source("trumpet_video2", TESTDATA / "trumpet_video2.mp4",
           wrong_notes=(NoteEdit(6, 3, "A#4", 16.78, 17.37, +1), NoteEdit(9, 3, "B3", 24.53, 24.81, -1)),
           missed_note=NoteEdit(16, 2.5, "C#5", 42.05, 42.33),
           rushed=Phrase((5, 8), 12.7, 22.9)),
)


def run_ffmpeg(args: list[str]) -> None:
    result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args],
                            capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise MakeTakesError(f"ffmpeg failed ({' '.join(args[:6])} ...): {result.stderr.strip()[-500:]}")


def read_audio(video: Path, workdir: Path) -> tuple[np.ndarray, int]:
    wav = workdir / "source.wav"
    run_ffmpeg(["-i", str(video), "-vn", "-c:a", "pcm_f32le", str(wav)])
    audio, rate = soundfile.read(wav, dtype="float32", always_2d=True)
    return audio.T, rate  # channels first, as librosa wants


def replace_span(audio: np.ndarray, rate: int, start_s: float, end_s: float, new_span: np.ndarray) -> np.ndarray:
    """Put `new_span` over audio[start_s:end_s], cross-fading FADE_S at both edges."""
    first, last = round(start_s * rate), round(end_s * rate)
    if not 0 <= first < last <= audio.shape[1] or new_span.shape[1] != last - first:
        raise MakeTakesError(f"Edit {start_s:.2f}-{end_s:.2f} s doesn't fit the {audio.shape[1] / rate:.2f} s recording.")
    fade = np.minimum(np.minimum(np.arange(last - first), np.arange(last - first)[::-1]) / (FADE_S * rate), 1.0)
    out = audio.copy()
    out[:, first:last] = audio[:, first:last] * (1 - fade) + new_span * fade
    return out


def note_span(note: NoteEdit) -> tuple[float, float]:
    return note.onset_s - NOTE_MARGIN_S, note.offset_s + note.tail_s


def shift_note(audio: np.ndarray, rate: int, note: NoteEdit) -> np.ndarray:
    start_s, end_s = note_span(note)
    context_start = max(0.0, start_s - SHIFT_CONTEXT_S)
    first, last = round(context_start * rate), round((end_s + SHIFT_CONTEXT_S) * rate)
    shifted = librosa.effects.pitch_shift(audio[:, first:last], sr=rate, n_steps=note.semitones)
    inner = shifted[:, round(start_s * rate) - first:round(end_s * rate) - first]
    return replace_span(audio, rate, start_s, end_s, inner)


def silence_note(audio: np.ndarray, rate: int, note: NoteEdit) -> np.ndarray:
    start_s, end_s = note_span(note)
    return replace_span(audio, rate, start_s, end_s, np.zeros((audio.shape[0], round(end_s * rate) - round(start_s * rate)), np.float32))


def speed_up_phrase(audio: np.ndarray, rate: int, phrase: Phrase) -> np.ndarray:
    first, last = round(phrase.start_s * rate), round(phrase.end_s * rate)
    faster = librosa.effects.time_stretch(audio[:, first:last], rate=RUSH_RATE)
    return np.concatenate([audio[:, :first], faster, audio[:, last:]], axis=1)


def wrong_note_audio(audio: np.ndarray, rate: int, source: Source) -> np.ndarray:
    for note in source.wrong_notes:
        audio = shift_note(audio, rate, note)
    return audio


def missed_and_rushing_audio(audio: np.ndarray, rate: int, source: Source) -> np.ndarray:
    inside = source.rushed.start_s <= source.missed_note.onset_s and source.missed_note.offset_s <= source.rushed.end_s
    if inside:
        raise MakeTakesError(f"{source.name}: the missed note must lie outside the rushed phrase.")
    return speed_up_phrase(silence_note(audio, rate, source.missed_note), rate, source.rushed)


def video_filter(phrase: Phrase | None) -> str:
    scale = f"scale=-2:{VIDEO_HEIGHT},fps=30000/1001"
    if phrase is None:
        return f"[0:v]{scale}[v]"
    start, end = phrase.start_s, phrase.end_s
    return (f"[0:v]trim=0:{start},setpts=PTS-STARTPTS[a];"
            f"[0:v]trim={start}:{end},setpts=(PTS-STARTPTS)/{RUSH_RATE}[b];"
            f"[0:v]trim=start={end},setpts=PTS-STARTPTS[c];"
            f"[a][b][c]concat=n=3:v=1:a=0,{scale}[v]")


def encode_take(video: Path, audio: np.ndarray, rate: int, phrase: Phrase | None, target: Path, workdir: Path) -> None:
    wav = workdir / f"{target.stem}.wav"
    soundfile.write(wav, audio.T, rate, subtype="FLOAT")
    target.parent.mkdir(parents=True, exist_ok=True)
    for crf in CRF_STEPS:
        run_ffmpeg(["-i", str(video), "-i", str(wav), "-filter_complex", video_filter(phrase), "-map", "[v]", "-map", "1:a",
                    "-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k", "-movflags", "+faststart", "-shortest", str(target)])
        if target.stat().st_size <= TARGET_BYTES:
            return
        logger.info("%s is %.1f MB at crf %s; trying a higher crf", target.name, target.stat().st_size / 1e6, crf)
    target.unlink()
    raise MakeTakesError(f"{target.name} is still over {MAX_BYTES / 1e6:.0f} MB at crf {CRF_STEPS[-1]}; lower VIDEO_HEIGHT.")


def make_source_takes(source: Source, out_dir: Path) -> list[Path]:
    if not source.video.is_file():
        raise MakeTakesError(f"Can't find the source recording {source.video}.")
    folder = out_dir / source.name
    takes = []
    with tempfile.TemporaryDirectory() as tmp:
        audio, rate = read_audio(source.video, Path(tmp))
        for suffix, make_audio, phrase in (("wrong_note", wrong_note_audio, None),
                                           ("missed_and_rushing", missed_and_rushing_audio, source.rushed)):
            target = folder / f"{source.name}_{suffix}.mp4"
            encode_take(source.video, make_audio(audio, rate, source), rate, phrase, target, Path(tmp))
            logger.info("wrote %s (%.1f MB)", target, target.stat().st_size / 1e6)
            takes.append(target)
    return takes


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=[source.name for source in SOURCES], help="make the takes of one source only")
    parser.add_argument("--out", type=Path, default=TESTDATA / "mistakes")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        for source in SOURCES:
            if args.only in (None, source.name):
                make_source_takes(source, args.out)
    except (MakeTakesError, OSError, soundfile.LibsndfileError) as error:
        logger.error("make_mistake_takes failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
