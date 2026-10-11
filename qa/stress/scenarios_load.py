"""Phases 1-9: 20 concurrent clients hitting every real route, N times each."""
import asyncio
import logging

import fixtures
import flows
from client import StressClient
from runner import PhaseRunner, fan_out

logger = logging.getLogger("stress.load")
WORKERS = 20
SCAN_POLL_S = 3
SCAN_WAIT_S = 120
VALID_PHOTO_SCANS = 3  # homr is a heavy subprocess per scan and nothing caps them; keep the laptop safe


async def _sessions(client: StressClient, rounds: int) -> None:
    async def job(_: int) -> None:
        for _round in range(rounds):
            session_id = await flows.new_session(client)
            if session_id:
                await client.call("GET /sessions/{id}", "GET", f"/sessions/{session_id}")
    await fan_out(WORKERS, job)


async def _reference_data(client: StressClient, rounds: int) -> None:
    async def job(_: int) -> None:
        for _round in range(rounds):
            await client.call("GET /builtins", "GET", "/builtins", params={"instrument": "violin"})
            await client.call("GET /reference-notes", "GET", "/reference-notes", params={"instrument": "trumpet"})
    await fan_out(WORKERS, job)


async def _score(client: StressClient, rounds: int) -> None:
    score_bytes = fixtures.SCORE_PATH.read_bytes()

    async def job(_: int) -> None:
        for _round in range(rounds):
            session_id = await flows.new_session(client)
            if not session_id:
                continue
            await client.call("POST /sessions/{id}/score/file (musicxml upload)", "POST", f"/sessions/{session_id}/score/file",
                              files={"file": ("score.musicxml", score_bytes, "application/xml")})
            await client.call("GET /sessions/{id}/score?format=musicxml", "GET", f"/sessions/{session_id}/score")
            await client.call("GET /sessions/{id}/score?format=json", "GET", f"/sessions/{session_id}/score", params={"format": "json"})
            await client.call("GET /sessions/{id}/score/status", "GET", f"/sessions/{session_id}/score/status")
            await flows.confirm(client, session_id)
            other = await flows.new_session(client)
            if other:
                await flows.pick_builtin(client, other)
    await fan_out(WORKERS, job)


async def _prepare_sessions(client: StressClient) -> list[str | None]:
    sessions: list[str | None] = [None] * WORKERS

    async def job(index: int) -> None:
        sessions[index] = await flows.confirmed_session(client)
    await fan_out(WORKERS, job)
    return sessions


async def _takes(client: StressClient, sessions: list[str | None], rounds: int) -> None:
    wav, webm = fixtures.sine_wav(), fixtures.wav_to_webm(fixtures.sine_wav())

    async def job(index: int) -> None:
        session_id = sessions[index]
        if not session_id:
            return
        for round_index in range(rounds):
            files = flows.wav_files(webm, "audio/webm", "take.webm") if round_index % 2 else flows.wav_files(wav)
            await flows.post_take(client, session_id, files=files)
        await asyncio.sleep(5)
        for take_id in (f"t{n}" for n in range(1, rounds + 1)):
            base = f"/sessions/{session_id}/takes/{take_id}"
            await client.call("GET /sessions/{id}/takes/{take}/analysis", "GET", f"{base}/analysis")
            await client.call("GET /sessions/{id}/takes/{take}/media", "GET", f"{base}/media")
            await client.call("GET /sessions/{id}/takes/{take}/feedback", "GET", f"{base}/feedback")
            await client.call("POST /sessions/{id}/takes/{take}/feedback (rerun)", "POST", f"{base}/feedback")
            await client.call("GET /sessions/{id}/takes/{take}/tracks", "GET", f"{base}/tracks")
        await client.call("POST /sessions/{id}/transposition", "POST", f"/sessions/{session_id}/transposition", json={"semitones": 2})
    await fan_out(WORKERS, job)


async def _calibration(client: StressClient, sessions: list[str | None], rounds: int) -> None:
    files = await flows.calibration_files(client)

    async def job(index: int) -> None:
        session_id = sessions[index]
        if not session_id:
            return
        for _round in range(rounds):
            await client.call("POST /sessions/{id}/calibration (live)", "POST", f"/sessions/{session_id}/calibration",
                              data={"click_at_s": "0.5"}, files=files)
            await client.call("POST /sessions/{id}/calibration/skip", "POST", f"/sessions/{session_id}/calibration/skip")
            await client.call("GET /sessions/{id}/calibration", "GET", f"/sessions/{session_id}/calibration")
    await fan_out(WORKERS, job)


async def _chat(client: StressClient, sessions: list[str | None], rounds: int) -> None:
    async def job(index: int) -> None:
        session_id = sessions[index]
        if not session_id:
            return
        for round_index in range(rounds):
            await client.call("POST /sessions/{id}/chat (AI off)", "POST", f"/sessions/{session_id}/chat", json={"message": f"How was take {round_index}?"})
            await client.call("GET /sessions/{id}/chat", "GET", f"/sessions/{session_id}/chat")
    await fan_out(WORKERS, job)


async def _camera_check(client: StressClient, sessions: list[str | None], rounds: int) -> None:
    frame = fixtures.PHOTO_PATH.read_bytes()

    async def job(index: int) -> None:
        if not sessions[index]:
            return
        for _round in range(rounds):
            await client.call("POST /sessions/{id}/camera-check", "POST", f"/sessions/{sessions[index]}/camera-check",
                              files={"file": ("frame.jpg", frame, "image/jpeg")})
    await fan_out(WORKERS, job)


async def _photos(client: StressClient) -> None:
    """20 rejected non-photos at once; one real scan alone (first run downloads homr's weights); then 3 real scans at once."""
    photo = fixtures.PHOTO_PATH.read_bytes()

    async def reject(_: int) -> None:
        session_id = await flows.new_session(client)
        if session_id:
            await client.call("POST /sessions/{id}/score/photo (not an image)", "POST", f"/sessions/{session_id}/score/photo",
                              files={"file": ("x.jpg", b"not an image at all", "image/jpeg")})
    await fan_out(WORKERS, reject)

    async def scan(_: int) -> None:
        session_id = await flows.new_session(client)
        if not session_id:
            return
        await client.call("POST /sessions/{id}/score/photo (real photo)", "POST", f"/sessions/{session_id}/score/photo",
                          files={"file": ("photo.jpg", photo, "image/jpeg")})
        for _ in range(SCAN_WAIT_S // SCAN_POLL_S):
            body = await client.json("GET /sessions/{id}/score/status", "GET", f"/sessions/{session_id}/score/status")
            if body and body.get("score_status") != "scanning":
                logger.info("Photo scan of %s ended as %s (%s)", session_id, body.get("score_status"), body.get("score_error"))
                return
            await asyncio.sleep(SCAN_POLL_S)
        logger.warning("Photo scan of %s still running after %d s", session_id, SCAN_WAIT_S)
    await fan_out(1, scan)
    await fan_out(VALID_PHOTO_SCANS, scan)


async def run_load_phases(client: StressClient, runner: PhaseRunner, rounds: int = 10) -> None:
    await runner.run("1 sessions create/get", lambda: _sessions(client, rounds * 4))
    await runner.run("2 builtins/reference notes", lambda: _reference_data(client, rounds * 4))
    await runner.run("3 score upload/confirm/read", lambda: _score(client, rounds))
    sessions: list[str | None] = []

    async def prepare() -> None:
        sessions.extend(await _prepare_sessions(client))
    await runner.run("4 prepare 20 confirmed sessions", prepare)
    await runner.run("5 takes upload + analysis reads", lambda: _takes(client, sessions, 8))
    await runner.run("6 calibration", lambda: _calibration(client, sessions, 5))
    await runner.run("7 chat", lambda: _chat(client, sessions, 8))
    await runner.run("8 camera check", lambda: _camera_check(client, sessions, 5))
    await runner.run("9 photo scans", lambda: _photos(client))
