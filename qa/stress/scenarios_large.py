"""Phase 10: big uploads (10, 50, 200 MB) streamed to takes, score files, photos and the camera check, one at a time."""
import asyncio
import logging

import fixtures
import flows
from client import StressClient
from config import MIB
from runner import PhaseRunner

logger = logging.getLogger("stress.large")
SIZES_MB = (10, 50, 200)
OVER_TAKE_LIMIT_MB = 201  # take limit is 200 MiB
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 16
TAKE_SETTLE_S = 12


async def _stream_upload(client: StressClient, route: str, path: str, filename: str, content_type: str, size_mb: int,
                         header: bytes = b"", fields: dict | None = None):
    total = size_mb * MIB
    headers, body = fixtures.multipart_stream("file", filename, content_type, fixtures.payload_chunks(total, header), total, fields)
    return await client.call(f"{route} {size_mb} MB", "POST", path, headers=headers, content=body)


async def _large_takes(client: StressClient) -> None:
    for size_mb in (*SIZES_MB, OVER_TAKE_LIMIT_MB):
        session_id = await flows.required_confirmed_session(client)
        header = fixtures.junk_wav_header(size_mb * MIB)
        response = await _stream_upload(client, "POST takes (wav)", f"/sessions/{session_id}/takes", "big.wav", "audio/wav",
                                        size_mb, header, flows.TAKE_FIELDS)
        if response is not None and response.status_code == 202:
            await asyncio.sleep(TAKE_SETTLE_S)
            analysis = await client.json("GET analysis after big take", "GET", f"/sessions/{session_id}/takes/t1/analysis")
            logger.info("Take %d MB settled as: %s", size_mb, analysis and (analysis.get("status"), analysis.get("error")))


async def _large_scores_and_photos(client: StressClient) -> None:
    for size_mb in (4, 6, 50, 200):
        session_id = await flows.required_session(client)
        await _stream_upload(client, "POST score/file (.musicxml)", f"/sessions/{session_id}/score/file", "big.musicxml", "application/xml", size_mb)
    for size_mb in SIZES_MB:
        session_id = await flows.required_session(client)
        await _stream_upload(client, "POST score/photo", f"/sessions/{session_id}/score/photo", "big.jpg", "image/jpeg", size_mb, JPEG_MAGIC)
    for size_mb in (10, 50):
        session_id = await flows.required_session(client)
        await _stream_upload(client, "POST camera-check", f"/sessions/{session_id}/camera-check", "big.jpg", "image/jpeg", size_mb, JPEG_MAGIC)


async def run_large_phases(client: StressClient, runner: PhaseRunner) -> None:
    await runner.run("10a large takes", lambda: _large_takes(client))
    await runner.run("10b large score/photo/camera uploads", lambda: _large_scores_and_photos(client))
