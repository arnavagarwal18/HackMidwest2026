"""Samples the server's resident memory (RSS) on an interval while a run is going."""
import asyncio
import logging
import subprocess
import time

from config import MEMORY_SAMPLE_INTERVAL_S

logger = logging.getLogger("stress.memory")


def rss_mb(pid: int) -> float | None:
    """RSS of the process in MB via `ps`, or None when the process is gone or ps fails."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        logger.exception("ps failed for pid %s", pid)
        return None
    return round(int(out) / 1024, 1) if out.isdigit() else None


def children_rss_mb(pid: int) -> float:
    """Total RSS of the process's direct child processes (ffmpeg, homr) in MB; 0 when there are none."""
    try:
        out = subprocess.run(["ps", "-A", "-o", "ppid=,rss="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        logger.exception("ps failed while looking for children of pid %s", pid)
        return 0.0
    kib = sum(int(rss) for ppid, rss in (line.split() for line in out.splitlines() if len(line.split()) == 2) if ppid == str(pid))
    return round(kib / 1024, 1)


class MemorySampler:
    def __init__(self, pid: int):
        self.pid = pid
        self.points: list[tuple[float, float, str]] = []  # (seconds since start, RSS MB, phase)
        self.peak_children_mb = 0.0
        self.phase = "start"
        self._started = time.monotonic()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            value = rss_mb(self.pid)
            if value is None:
                logger.error("Server pid %s is not running any more (sample at %.0f s)", self.pid, time.monotonic() - self._started)
                self.points.append((round(time.monotonic() - self._started, 1), 0.0, "PROCESS GONE"))
            else:
                self.points.append((round(time.monotonic() - self._started, 1), value, self.phase))
            self.peak_children_mb = max(self.peak_children_mb, children_rss_mb(self.pid))
            await asyncio.sleep(MEMORY_SAMPLE_INTERVAL_S)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def summary(self) -> dict:
        values = [v for _, v, phase in self.points if phase != "PROCESS GONE"]
        by_phase: dict[str, float] = {}
        for _, value, phase in self.points:
            by_phase[phase] = max(by_phase.get(phase, 0.0), value)
        return {"start_mb": values[0] if values else None, "peak_mb": max(values, default=None), "end_mb": values[-1] if values else None, "samples": len(self.points),
                "peak_by_phase_mb": by_phase, "peak_children_mb": self.peak_children_mb, "process_gone": any(p == "PROCESS GONE" for _, _, p in self.points)}
