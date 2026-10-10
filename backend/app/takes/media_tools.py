"""ffmpeg helpers: probe duration and audio stream from `ffmpeg -i` output, extract 16 kHz mono wav."""
import logging
import re
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

logger = logging.getLogger("app.takes.media")

FFMPEG_TIMEOUT_S = 60
_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_AUDIO_STREAM = re.compile(r"Stream #\S+.*?:\s*Audio:")


class MediaError(Exception):
    """A take's media couldn't be processed; `code` is stored as the take's error."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass
class MediaInfo:
    duration_s: float | None  # None when the container doesn't say (common for browser WebM)
    has_audio: bool


def ffmpeg_exe() -> str:
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except RuntimeError as exc:
        logger.error("ffmpeg binary not found: %s", exc)
        raise MediaError("decode_failed", f"ffmpeg is not available: {exc}") from exc


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    command = [ffmpeg_exe(), *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=FFMPEG_TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        logger.error("ffmpeg timed out after %s s: %s", FFMPEG_TIMEOUT_S, args)
        raise MediaError("decode_failed", "ffmpeg timed out") from exc
    except OSError as exc:
        logger.error("ffmpeg could not be started: %s", exc)
        raise MediaError("decode_failed", f"ffmpeg could not be started: {exc}") from exc


def parse_media_info(ffmpeg_stderr: str) -> MediaInfo | None:
    """Read duration and audio-stream presence from `ffmpeg -i` stderr; None if it isn't media."""
    has_audio = bool(_AUDIO_STREAM.search(ffmpeg_stderr))
    match = _DURATION.search(ffmpeg_stderr)
    if match is None and "Stream #" not in ffmpeg_stderr:
        return None
    duration = None
    if match:
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return MediaInfo(duration_s=duration, has_audio=has_audio)


def probe(path: Path) -> MediaInfo:
    result = _run_ffmpeg(["-hide_banner", "-i", str(path)])
    info = parse_media_info(result.stderr)
    if info is None:
        logger.error("ffmpeg could not read %s: %s", path, result.stderr.strip()[-500:])
        raise MediaError("decode_failed", "ffmpeg could not read the file")
    return info


def extract_wav(source: Path, target: Path) -> None:
    result = _run_ffmpeg(["-hide_banner", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(target)])
    if result.returncode != 0 or not target.is_file():
        logger.error("ffmpeg failed on %s (exit %s): %s", source, result.returncode, result.stderr.strip()[-500:])
        raise MediaError("decode_failed", "ffmpeg could not extract the audio")


def wav_duration_s(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
    except (wave.Error, OSError, EOFError, ZeroDivisionError) as exc:
        logger.error("Could not read extracted wav %s: %s", path, exc)
        raise MediaError("decode_failed", "the extracted audio could not be read") from exc
