"""The steps of the live Bedrock smoke test. Each returns StepResult rows and never raises.

The feedback and chat steps go through the FastAPI routes, so they run exactly what the browser would. Only the take flow reuses
e2e_real's helpers (its Steps timer and its score and take uploads), which work on any httpx client, a TestClient included.
"""
import json
import logging
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import e2e_real
from fastapi.testclient import TestClient

from app import store
from live_smoke_report import FAIL, PASS, StepResult, checker_verdict

logger = logging.getLogger("live_bedrock_smoke")

TESTDATA = Path(__file__).resolve().parents[2] / "testdata"
SCORE_FILE = TESTDATA / "ode_to_joy" / "score.musicxml"
VIDEO = TESTDATA / "ode_to_joy" / "ode_to_joy_trumpet11.mp4"
ODE_BARS = (1, 16)  # the clip plays the whole piece: 16 bars at quarter = 100
CHAT_MESSAGE = "What should I work on first?"

ERROR_CLASS = re.compile(r"error: (\w+)")


def _crashed(result: StepResult, exc: Exception, started: float) -> StepResult:
    result.latency_s, result.reason, result.error_class = time.monotonic() - started, "step_crashed", type(exc).__name__
    result.note = "see the log file next to the results"
    return result


def _fallback_error_class(events: list[dict]) -> str | None:
    """The class of the error the run recorded when it fell back (run.py writes 'error: <Class>' in the fallback event)."""
    for event in events:
        match = ERROR_CLASS.search(event["detail"]) if event.get("event") == "fallback" else None
        if match:
            return match.group(1)
    return None


def _planner_reason(events: list[dict], coach_reason: str | None) -> str:
    if coach_reason in ("timeout", "model_error", "disabled"):
        return coach_reason  # the whole run failed or never started, so the Planner did too
    if checker_verdict(events, "submit_plan") is False:
        return "checker_rejected"
    if any(e.get("agent") == "planner" and e.get("event") == "error" for e in events):
        return "model_error"
    return "planner_not_run"


def feedback_results(client: TestClient, session_id: str, feedback: dict) -> list[StepResult]:
    """(b) The Coach and the Planner rows for one saved feedback record, judged from the record and its trace."""
    traced = client.get(f"/sessions/{session_id}/feedback/{feedback['id']}/trace")
    events = traced.json()["events"] if traced.status_code == 200 else []
    if traced.status_code != 200:
        logger.error("No trace for feedback %s (HTTP %s)", feedback["id"], traced.status_code)
    seconds, plan = feedback["duration_ms"] / 1000, feedback["plan"]
    coach_ok, plan_ok = feedback["mode"] == "ai", plan["mode"] == "ai"
    error_class = _fallback_error_class(events)
    coach = StepResult("feedback: coach", PASS if coach_ok else FAIL, seconds, checker_verdict(events, "submit_feedback"),
                       feedback["mode"], feedback["fallback_reason"], None if coach_ok else error_class,
                       f"{len(feedback['sentences'])} sentences; latency is the whole feedback run")
    planner = StepResult("feedback: planner", PASS if plan_ok else FAIL, seconds, checker_verdict(events, "submit_plan"), plan["mode"],
                         None if plan_ok else _planner_reason(events, feedback["fallback_reason"]), None if plan_ok else error_class,
                         f"{len(plan['exercises'])} exercises; runs in parallel with the coach")
    if traced.status_code != 200:
        coach.note += "; no trace, so the Checker verdict is unknown"
    return [coach, planner]


def _chat_events(session_id: str, turn_id: str) -> list[dict]:
    path = store.session_dir(session_id) / f"{turn_id}_trace.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Could not read the chat trace %s", path)
        return []


def chat_step(client: TestClient, session_id: str, message: str = CHAT_MESSAGE) -> StepResult:
    """(c) One Instructor chat turn on the session's latest take."""
    result, started = StepResult("instructor chat"), time.monotonic()
    try:
        response = client.post(f"/sessions/{session_id}/chat", json={"message": message})
        result.latency_s = time.monotonic() - started
        if response.status_code != 200:
            logger.error("Chat answered HTTP %s: %s", response.status_code, response.text[:300])
            result.reason = f"http_{response.status_code}"
            return result
        turn = response.json()["instructor_turn"]
        result.mode, result.reason = turn["mode"], turn["fallback_reason"]
        result.checker_accepted = checker_verdict(_chat_events(session_id, turn["id"]), "submit_reply")
        result.status = PASS if turn["mode"] == "ai" else FAIL
        result.note = f"{len(turn['sentences'])} sentences"
    except Exception as exc:
        logger.exception("Chat step crashed")
        return _crashed(result, exc, started)
    return result


def take_flow(client: TestClient) -> tuple[str, str]:
    """Create a trumpet session, confirm the Ode to Joy score, upload the Ode to Joy take and wait for it to be done.

    With AI on, the take's own pipeline runs the feedback agents, so a finished take already has its live feedback.
    Returns (session_id, take_id); raises E2EError on any failed step.
    """
    steps = e2e_real.Steps()
    session_id = steps.run("create session", lambda: client.post("/sessions", json={"instrument": "trumpet"})).json()["session_id"]
    e2e_real.upload_score_file(client, steps, session_id, SCORE_FILE)
    confirmed = steps.run("confirm score", lambda: client.post(f"/sessions/{session_id}/score/confirm")).json()
    take_id = e2e_real.upload_take(client, steps, session_id, SimpleNamespace(video=VIDEO, bars=ODE_BARS, bpm=None), confirmed)
    route = f"/sessions/{session_id}/takes/{take_id}/analysis"
    analysis = steps.poll("take analysis and feedback", lambda: client.get(route), lambda b: b["status"] in ("done", "failed"),
                          e2e_real.TAKE_TIMEOUT_S)
    if analysis["status"] != "done":
        raise e2e_real.E2EError(f"The take ended as '{analysis['status']}' (error code {analysis['error']}).")
    return session_id, take_id


def feedback_step(client: TestClient, session_id: str, take_id: str) -> list[StepResult]:
    """(b) Read the take's feedback and judge the Coach and the Planner."""
    started = time.monotonic()
    try:
        response = client.get(f"/sessions/{session_id}/takes/{take_id}/feedback")
        if response.status_code != 200:
            logger.error("Feedback answered HTTP %s: %s", response.status_code, response.text[:300])
            reason = f"http_{response.status_code}"
            return [StepResult(name, reason=reason) for name in ("feedback: coach", "feedback: planner")]
        return feedback_results(client, session_id, response.json())
    except Exception as exc:
        logger.exception("Feedback step crashed")
        return [_crashed(StepResult(name), exc, started) for name in ("feedback: coach", "feedback: planner")]


def guarded(step: str, call: Callable[[], object]) -> tuple[object | None, StepResult | None]:
    """(call's value, None), or (None, a failed row) when it raised: the error is logged and its class shown."""
    started = time.monotonic()
    try:
        return call(), None
    except Exception as exc:
        logger.exception("%s failed", step)
        return None, _crashed(StepResult(step), exc, started)
