"""Test inputs: small valid media, junk of any size, and a streamed multipart body for big uploads."""
import io
import subprocess
import uuid
from typing import AsyncIterator, Iterator

import imageio_ffmpeg
import numpy as np
import soundfile as sf

from config import REPO_ROOT

SAMPLE_RATE = 16000
PHOTO_PATH = REPO_ROOT / "testdata" / "ode_to_joy_photo.jpg"
SCORE_PATH = REPO_ROOT / "testdata" / "ode_to_joy" / "score.musicxml"
CHUNK = 1024 * 1024


def sine_wav(hz: float = 440.0, seconds: float = 2.0, burst_at_s: float | None = None) -> bytes:
    """A 16 kHz wav of a quiet-padded sine note, or (with burst_at_s) a click burst at that time."""
    rng = np.random.default_rng(1)
    audio = rng.normal(0, 3e-4, int(seconds * SAMPLE_RATE))
    t = np.arange(len(audio)) / SAMPLE_RATE
    if burst_at_s is None:
        audio[int(0.4 * SAMPLE_RATE):-int(0.4 * SAMPLE_RATE)] += 0.3 * np.sin(2 * np.pi * hz * t[int(0.4 * SAMPLE_RATE):-int(0.4 * SAMPLE_RATE)])
    else:
        start = int(burst_at_s * SAMPLE_RATE)
        audio[start:start + 80] += 0.5 * np.sin(2 * np.pi * 2000 * np.arange(80) / SAMPLE_RATE)
    buffer = io.BytesIO()
    sf.write(buffer, audio.astype(np.float32), SAMPLE_RATE, format="WAV")
    return buffer.getvalue()


def wav_to_webm(wav: bytes) -> bytes:
    """Encode wav bytes as opus-in-webm with the bundled ffmpeg."""
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-c:a", "libopus", "-f", "webm", "pipe:1"],
        input=wav, capture_output=True, check=True,
    )
    return result.stdout


def junk_wav_header(total_bytes: int) -> bytes:
    """A valid 44-byte PCM wav header claiming total_bytes of file (16-bit mono 44.1 kHz)."""
    data_bytes = max(total_bytes - 44, 0)
    return (b"RIFF" + (data_bytes + 36).to_bytes(4, "little") + b"WAVEfmt " + (16).to_bytes(4, "little")
            + (1).to_bytes(2, "little") + (1).to_bytes(2, "little") + (44100).to_bytes(4, "little")
            + (88200).to_bytes(4, "little") + (2).to_bytes(2, "little") + (16).to_bytes(2, "little")
            + b"data" + data_bytes.to_bytes(4, "little"))


def payload_chunks(total_bytes: int, header: bytes = b"") -> Iterator[bytes]:
    """total_bytes of generated payload (header, then a repeating pattern), 1 MiB at a time; never held whole in memory."""
    block = bytes(range(256)) * (CHUNK // 256)
    remaining = total_bytes - len(header)
    if header:
        yield header
    while remaining > 0:
        piece = block[:min(CHUNK, remaining)]
        remaining -= len(piece)
        yield piece


def multipart_stream(field: str, filename: str, content_type: str, chunks: Iterator[bytes], payload_bytes: int,
                     extra_fields: dict[str, str] | None = None) -> tuple[dict, AsyncIterator[bytes]]:
    """Headers (with Content-Length) and a body generator for a multipart upload whose file part is streamed."""
    boundary = uuid.uuid4().hex
    head = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in (extra_fields or {}).items()
    ) + (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
         f"Content-Type: {content_type}\r\n\r\n").encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    headers = {"content-type": f"multipart/form-data; boundary={boundary}",
               "content-length": str(len(head) + payload_bytes + len(tail))}

    async def body():
        yield head
        for chunk in chunks:
            yield chunk
        yield tail
    return headers, body()
