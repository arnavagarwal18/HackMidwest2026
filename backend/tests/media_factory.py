"""Generate small test media with the bundled ffmpeg binary."""
import subprocess
from pathlib import Path

import imageio_ffmpeg

_AUDIO_INPUT = ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100"]
_SILENCE_INPUT = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
_VIDEO_INPUT = ["-f", "lavfi", "-i", "testsrc=size=160x120:rate=10"]


def _ffmpeg(*args: str) -> None:
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def make_wav(path: Path, seconds: float = 1.0, silent: bool = False) -> Path:
    _ffmpeg(*(_SILENCE_INPUT if silent else _AUDIO_INPUT), "-t", str(seconds), str(path))
    return path


def make_webm_audio(path: Path, seconds: float = 1.0) -> Path:
    _ffmpeg(*_AUDIO_INPUT, "-t", str(seconds), "-c:a", "libopus", str(path))
    return path


def make_silent_video_mp4(path: Path, seconds: float = 1.0) -> Path:
    _ffmpeg(*_VIDEO_INPUT, "-t", str(seconds), "-an", "-pix_fmt", "yuv420p", str(path))
    return path


_AV_CODECS = {
    ".mp4": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"],
    ".webm": ["-c:v", "libvpx", "-c:a", "libopus"],
}


def make_video_with_audio(path: Path, audio_wav: Path) -> Path:
    """Mux a small test picture with the given wav into the container the path's extension names (.mp4 or .webm)."""
    _ffmpeg(*_VIDEO_INPUT, "-i", str(audio_wav), "-shortest", *_AV_CODECS[path.suffix], str(path))
    return path
