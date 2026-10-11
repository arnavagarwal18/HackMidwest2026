"""Entry point: python run_stress.py --pid <uvicorn pid> [--base-url http://127.0.0.1:8110] [--skip-large]

Starts nothing and stops nothing: the server is started by hand on your own port. Writes out/results.json.
"""
import argparse
import asyncio
import json
import logging
import shutil
import time
from pathlib import Path

from client import StressClient
from config import BASE_URL, HANG_THRESHOLD_S, RESULTS_JSON, SESSIONS_DIR, check_base_url
from memory import MemorySampler
from runner import PhaseRunner
from scenarios_large import run_large_phases
from scenarios_load import run_load_phases
from scenarios_leak import run_leak_check
from scenarios_malformed import run_malformed
from scenarios_sessions import run_sessions
from stats import Recorder

logger = logging.getLogger("stress")


def clear_sessions() -> None:
    """Delete this run's session folders (the data dir is inside the worktree), keeping .gitkeep."""
    for entry in SESSIONS_DIR.iterdir():
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)


def disk_mb() -> float:
    return round(sum(f.stat().st_size for f in SESSIONS_DIR.rglob("*") if f.is_file()) / (1024 * 1024), 1)


ALL_PARTS = ("load", "large", "malformed", "sessions", "leak")


async def main(pid: int, base_url: str, parts: tuple[str, ...], out_file: Path) -> None:
    recorder = Recorder()
    client = StressClient(check_base_url(base_url), recorder)
    sampler = MemorySampler(pid)
    runner = PhaseRunner(client, sampler)
    sampler.start()
    started = time.monotonic()
    results: dict = {}
    try:
        await asyncio.sleep(3)
        if "load" in parts:
            await run_load_phases(client, runner)
            results["disk_after_load_mb"] = disk_mb()
        if "large" in parts:
            await run_large_phases(client, runner)
            results["disk_after_large_mb"] = disk_mb()
        if "malformed" in parts:
            sampler.phase = "11 malformed"
            results["malformed"] = await run_malformed(client)
        if "sessions" in parts:
            sampler.phase = "12 session edge cases"
            results["sessions"] = await run_sessions(client)
        if "leak" in parts:
            sampler.phase = "13 leak check"
            results["leak_check"] = await run_leak_check(client, pid)
        sampler.phase = "cooldown"
        await asyncio.sleep(10)
    finally:  # results are written even when a part crashes, so a late failure doesn't lose the earlier numbers
        await sampler.stop()
        await client.close()
        results.update(
            hangs_over_limit=sum(s.latency_s > HANG_THRESHOLD_S for s in recorder.samples),
            no_response=sum(s.status is None for s in recorder.samples), total_requests=len(recorder.samples),
            phases=runner.phases, memory=sampler.summary(), memory_points=sampler.points[::3], total_s=round(time.monotonic() - started, 1),
        )
        out_file.parent.mkdir(exist_ok=True)
        out_file.write_text(json.dumps(results, indent=1), encoding="utf-8")
        logger.info("Wrote %s (total %.0f s)", out_file, results["total_s"])
        clear_sessions()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", type=int, required=True, help="PID of the uvicorn process you started")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--only", default=",".join(ALL_PARTS), help=f"comma list of: {', '.join(ALL_PARTS)}")
    parser.add_argument("--out", default=str(RESULTS_JSON), help="where to write the results JSON")
    args = parser.parse_args()
    parts = tuple(args.only.split(","))
    unknown = set(parts) - set(ALL_PARTS)
    if unknown:
        raise SystemExit(f"Unknown part(s) {sorted(unknown)}; choose from {ALL_PARTS}")
    asyncio.run(main(args.pid, args.base_url, parts, Path(args.out)))
