"""Results of the live Bedrock smoke test: one row per step, a stdout table and a JSON file.

Rows hold reason codes and error class names only, never a setting value, a model id or an error message.
"""
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("live_bedrock_smoke")

PASS, FAIL, SKIPPED = "pass", "fail", "skipped"
CHECKER_COLUMN = {True: "accepted", False: "rejected", None: "n/a"}


@dataclass
class StepResult:
    step: str
    status: str = FAIL
    latency_s: float | None = None
    checker_accepted: bool | None = None  # None when no Checker judges this step's output
    mode: str | None = None  # 'ai' or 'fallback', for the agents that have a fallback
    reason: str | None = None  # the fallback or failure code, e.g. checker_rejected, timeout, model_error
    error_class: str | None = None
    note: str = ""

    @property
    def passed(self) -> bool:
        return self.status == PASS


def skipped(step: str, why: str) -> StepResult:
    return StepResult(step, SKIPPED, reason="skipped", note=why)


def trace_check_names(events: list[dict], event: str) -> set[str]:
    """The submit tools whose output the Checker answered with `event` ('check_pass' or 'check_fail') in this trace."""
    return {e["name"] for e in events if e.get("agent") == "checker" and e.get("event") == event}


def checker_verdict(events: list[dict], submit_tool: str) -> bool | None:
    """True when the Checker accepted what `submit_tool` submitted, False when it only ever rejected it, None when nothing was submitted."""
    if submit_tool in trace_check_names(events, "check_pass"):
        return True
    return False if submit_tool in trace_check_names(events, "check_fail") else None


def table_lines(results: list[StepResult]) -> list[str]:
    header = ("step", "result", "seconds", "checker", "mode", "reason")
    rows = [header] + [
        (r.step, r.status, "-" if r.latency_s is None else f"{r.latency_s:.1f}", CHECKER_COLUMN[r.checker_accepted],
         r.mode or "-", r.reason or r.error_class or "-")
        for r in results
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(len(header))]
    return ["  ".join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows]


def write_json(path: Path, payload: dict) -> bool:
    """Save the run; a failure is logged and reported to the caller, which prints where the table went instead."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except OSError:
        logger.exception("Could not write the results to %s", path)
        return False


def payload_of(results: list[StepResult], settings_presence: dict[str, bool], started_at: str) -> dict:
    return {"started_at": started_at, "all_passed": all(r.passed for r in results),
            "settings_present": settings_presence, "steps": [asdict(r) for r in results]}
