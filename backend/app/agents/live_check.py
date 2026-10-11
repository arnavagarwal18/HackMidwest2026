"""One-command live check of the feedback agents on Bedrock: run `python -m app.agents.live_check` from backend/.

Runs the real pipeline (the Orchestrator, then the Coach and Planner in parallel, each submit judged by the Checker)
on the repo's test trumpet take, prints the time of each stage and saves the trace as a sample for the judges.
It makes one run and never retries; any failure prints one line and exits 1.
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path

from strands.agent import agent as strands_agent

from app.agents import ai_run
from app.agents.config import ConfigError, get_settings
from app.agents.credentials import first_credential_error
from app.agents.holder import RunHolder
from app.agents.model import build_agent_model
from app.agents.smoke_errors import describe_config_error, describe_failure
from app.agents.trace import Trace

logger = logging.getLogger("app.agents.live_check")
BACKEND_DIR = Path(__file__).resolve().parents[2]
LOG_FILE = BACKEND_DIR / "live_check.log"
TAKE_FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "diagnosis_fixture.json"  # the diagnosed trumpet take the agent tests use
DEFAULT_TRACE_PATH = Path(__file__).resolve().parent / "samples" / "live_trace.json"
SUBMIT_TOOLS = ("submit_feedback", "submit_plan")


@contextmanager
def single_shot():
    """For the agents built inside the block: no botocore retry (max_attempts 0) and one Strands model attempt, so a throttled call fails at once.

    The shared defaults (botocore AGENT_RETRIES, Strands' 6 attempts with 4 s+ waits) stay as they are for the app;
    only this one-shot command spends no extra Bedrock quota on retries.
    """
    original_model, original_attempts = ai_run.build_agent_model, strands_agent.MAX_ATTEMPTS
    ai_run.build_agent_model, strands_agent.MAX_ATTEMPTS = partial(build_agent_model, attempts=0), 1
    try:
        yield
    finally:
        ai_run.build_agent_model, strands_agent.MAX_ATTEMPTS = original_model, original_attempts


def load_take() -> tuple[str, dict, list[dict]]:
    """(session_id, take, history) of the test take, in the shape run_agents takes."""
    data = json.loads(TAKE_FIXTURE.read_text(encoding="utf-8"))
    take = {"take_id": data["take_id"], "diagnosis": data["diagnosis"], "form": data["form"]}
    return data["session_id"], take, data["history"]


def _agent_span(events: list[dict], agent: str) -> tuple[int, int] | None:
    times = [e["t_ms"] for e in events if e["agent"] == agent]
    return (min(times), max(times)) if times else None


def stage_lines(events: list[dict], total_ms: int) -> list[str]:
    """One line per stage, from the trace: how long it ran, and how many model calls or checks it made."""
    model_calls = lambda agent: sum(1 for e in events if e["agent"] == agent and e["event"] == "model_start")
    starts = [span[0] for span in (_agent_span(events, a) for a in ("coach", "planner")) if span]
    orchestrator_end = min(starts) if starts else total_ms
    lines = [f"orchestrator  {orchestrator_end:>6} ms  ({model_calls('orchestrator')} model calls, until it hands over to the Coach and Planner)"]
    for agent in ("coach", "planner"):
        span = _agent_span(events, agent)
        lines.append(f"{agent:<13} {span[1] - span[0] if span else 0:>6} ms  ({model_calls(agent)} model calls, in parallel)")
    checks = [e for e in events if e["agent"] == "checker"]
    check_ms = sum(e["duration_ms"] for e in events if e["event"] == "tool_end" and e["name"] in SUBMIT_TOOLS)
    failed = sum(1 for e in checks if e["event"] == "check_fail")
    lines.append(f"checker       {check_ms:>6} ms  ({len(checks)} checks, {failed} failed; time is inside the Coach and Planner)")
    lines.append(f"total         {total_ms:>6} ms")
    return lines


def _first_failure(failure: BaseException | None, holder: RunHolder) -> BaseException | None:
    errors = [failure] if failure is not None else [*holder.errors, *holder.planner_errors]
    return first_credential_error(errors) or (errors[0] if errors else None)


def _failure_line(failure: BaseException | None, holder: RunHolder) -> str | None:
    """The one-line reason the run did not produce accepted Coach feedback and a Planner plan, or None when it did."""
    error = _first_failure(failure, holder)
    if isinstance(error, asyncio.TimeoutError):
        return f"The agents did not finish within {ai_run.TIME_LIMIT_S} s."
    if error is not None:
        return describe_failure(error, "feedback agents", get_settings().text_model, get_settings())
    if holder.feedback is None or holder.plan is None:
        missing = "Coach feedback" if holder.feedback is None else "Planner plan"
        return f"The Checker accepted no {missing} (coach tries {holder.coach_tries}, planner tries {holder.planner_tries})."
    return None


def _save_trace(trace: Trace, path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        logger.exception("Could not create the folder for the trace %s", path)
        return False
    return trace.save(path)


def run_live_check(trace_path: Path) -> int:
    """Run the agents once on the test take, print the timings and save the trace. Returns the exit code."""
    try:
        settings = get_settings()
        if not settings.ai_enabled:
            raise ConfigError("AI is switched off (AI_ENABLED is not true). Set AI_ENABLED=true.")
    except ConfigError as exc:
        print(f"FAILED: {describe_config_error(exc)}", file=sys.stderr)
        return 1
    session_id, take, history = load_take()
    holder, trace, failure, started = RunHolder(), Trace(), None, time.monotonic()
    try:
        with single_shot():
            asyncio.run(ai_run.run_agents(session_id, take, history, holder, trace))
    except Exception as exc:
        failure = exc
        logger.error("The live check failed", exc_info=exc)
    total_ms = round((time.monotonic() - started) * 1000)
    print("\n".join(stage_lines(trace.events, total_ms)))
    reason = _failure_line(failure, holder)
    if reason:
        logger.error("The live check ended without a full result: %s", reason)
        print(f"FAILED: {reason} (details: {LOG_FILE.name})", file=sys.stderr)
        return 1
    if not _save_trace(trace, trace_path):
        print(f"FAILED: Could not write the trace to {trace_path} (details: {LOG_FILE.name})", file=sys.stderr)
        return 1
    print(f"OK: {len(holder.feedback['sentences'])} Coach sentences, {len(holder.plan['exercises'])} exercises; trace saved to {trace_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the feedback agents once on Bedrock and save the trace.")
    parser.add_argument("--trace-out", type=Path, default=DEFAULT_TRACE_PATH, help="where to save the trace JSON (default: %(default)s)")
    logging.basicConfig(level=logging.ERROR, filename=LOG_FILE, filemode="w")
    return run_live_check(parser.parse_args(argv).trace_out)


if __name__ == "__main__":
    sys.exit(main())
