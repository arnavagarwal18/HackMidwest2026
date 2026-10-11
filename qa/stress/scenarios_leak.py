"""Phase 13: does memory come back down? Repeated rounds of sessions, each followed by an idle pause and an RSS reading."""
import asyncio

import flows
from client import StressClient
from memory import rss_mb
from runner import fan_out

WORKERS = 20
ROUNDS = 4
SESSIONS_PER_WORKER = 75
IDLE_S = 6


async def _create_sessions(client: StressClient) -> None:
    async def job(_: int) -> None:
        for _round in range(SESSIONS_PER_WORKER):
            session_id = await flows.new_session(client)
            if session_id:
                await client.call("leak: GET /sessions/{id}", "GET", f"/sessions/{session_id}")
    await fan_out(WORKERS, job)


async def run_leak_check(client: StressClient, pid: int) -> dict:
    """RSS after each round of 1500 new sessions (the store keeps every session in memory for the life of the process)."""
    readings = [rss_mb(pid)]
    for _ in range(ROUNDS):
        await _create_sessions(client)
        await asyncio.sleep(IDLE_S)
        readings.append(rss_mb(pid))
    return {"sessions_per_round": WORKERS * SESSIONS_PER_WORKER, "rss_mb_before_then_after_each_round": readings}
