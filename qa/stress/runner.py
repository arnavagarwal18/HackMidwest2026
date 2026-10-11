"""Runs named phases of load: every phase is timed, tagged for the memory sampler, and summarized per route."""
import asyncio
import logging
import time
from typing import Awaitable, Callable

from client import StressClient
from memory import MemorySampler
from stats import summarize

logger = logging.getLogger("stress.runner")


class PhaseRunner:
    def __init__(self, client: StressClient, sampler: MemorySampler):
        self.client = client
        self.sampler = sampler
        self.phases: dict[str, dict] = {}

    async def run(self, name: str, work: Callable[[], Awaitable[None]]) -> None:
        """Run `work`, then store the wall time and per-route numbers of the requests it made."""
        recorder = self.client.recorder
        first, started = len(recorder.samples), time.monotonic()
        self.sampler.phase = name
        try:
            await work()
        except Exception:
            logger.exception("Phase %s crashed", name)
            self.phases[name] = {"crashed": True}
            return
        wall = time.monotonic() - started
        made = recorder.samples[first:]
        self.phases[name] = {
            "wall_s": round(wall, 2),
            "routes": {route: summarize([s for s in made if s.route == route], wall) for route in dict.fromkeys(s.route for s in made)},
        }
        logger.info("Phase %s: %d requests in %.1f s", name, len(made), wall)


async def fan_out(workers: int, job: Callable[[int], Awaitable[None]]) -> None:
    """Run job(worker_index) for each worker at once; a failing worker is logged and doesn't stop the others."""
    async def guarded(index: int) -> None:
        try:
            await job(index)
        except Exception:
            logger.exception("Worker %d crashed", index)
    await asyncio.gather(*(guarded(i) for i in range(workers)))
