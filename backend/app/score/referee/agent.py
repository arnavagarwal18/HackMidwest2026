"""The referee: a vision model settles the bars where homr and the reader agent disagree.

run() never raises. If the referee is skipped or fails, the inputs come back unchanged (rulings
accepted before a failure are still applied) and the report says why. The model's agent comes
from an injectable factory, so tests use a stub that calls the session's tools in a fixed order;
the real Strands/Bedrock path is build_strands_agent.
"""
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from strands import Agent

from app.agents.config import ConfigError, Settings, get_settings
from app.agents.model import build_bedrock_model
from app.agents.trace import Trace
from app.score.compare import MOSTLY_DIFFERENT_WARNING, CompareResult
from app.score.model import Score
from app.score.reading import Reading
from app.score.referee import config
from app.score.referee.apply import apply_rulings
from app.score.referee.result import RefereeReport, RefereeResult, Ruling
from app.score.referee.tools import BarBox, RefereeSession

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a referee between two readings of a photo of trumpet music: 'homr' and 'reader'. They "
    "disagree on some bars. For each doubtful bar: call get_bar to see both readings and their code "
    "checks; call look_at_bar when the checks do not settle it; then call submit_ruling once with "
    "pick 'homr', 'reader' or 'neither', a short reason, and your confidence from 0 to 1. Prefer a "
    "reading whose checks all pass. Pick 'neither' when you are not sure. Never invent notes. "
    "Start with list_doubtful_bars. Stop when every doubtful bar has a ruling."
)
FIRST_PROMPT = "Referee the doubtful bars of this score."

AgentRun = Callable[[str, threading.Event], object]
AgentFactory = Callable[[Settings, RefereeSession, float], AgentRun]


def build_strands_agent(settings: Settings, session: RefereeSession, timeout_s: float) -> AgentRun:
    """The real referee: a Strands agent on the Bedrock vision model with this session's four tools."""
    model = build_bedrock_model(settings, settings.vision_model, timeout_seconds=max(1, int(timeout_s)))
    model.update_config(max_tokens=config.MAX_OUTPUT_TOKENS)
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=session.strands_tools(), callback_handler=None)
    return lambda prompt, cancel: agent(prompt, cancel_signal=cancel)


def _run_with_timeout(agent_run: AgentRun, cancel: threading.Event, timeout_s: float) -> None:
    """Run the agent in a daemon thread so a hung call cannot hold the caller past timeout_s (the caller cancels it)."""
    outcome: dict = {}

    def work() -> None:
        try:
            agent_run(FIRST_PROMPT, cancel)
        except BaseException as exc:  # reported by the caller; a thread must not die silently
            outcome["error"] = exc

    worker = threading.Thread(target=work, name="score-referee", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise TimeoutError(f"the referee took longer than {timeout_s:g} seconds")
    if "error" in outcome:
        raise outcome["error"]


def _report(status: str, reason: str | None, rulings: list[Ruling], model_id: str | None, started: float) -> RefereeReport:
    return RefereeReport(status=status, reason=reason, rulings=rulings, model_id=model_id,
                         elapsed_ms=round((time.monotonic() - started) * 1000))


def _skip_reason(compare: CompareResult, settings: Settings | None) -> str | None:
    if MOSTLY_DIFFERENT_WARNING in compare.warnings:
        return "mostly_different"
    if not compare.doubtful_bars:
        return "nothing_to_check"
    if settings is None or not settings.ai_enabled:
        return "ai_off"
    return None


def _settings_or_none() -> Settings | None:
    try:
        return get_settings()
    except ConfigError:
        logger.exception("Score referee: AI settings are wrong, so the referee is skipped")
        return None


def run(
    score: Score,
    reading: Reading,
    compare: CompareResult,
    image_path: Path,
    *,
    trace: Trace | None = None,
    bar_boxes: dict[int, BarBox] | None = None,
    agent_factory: AgentFactory = build_strands_agent,
    timeout_s: float = config.TIMEOUT_S,
) -> RefereeResult:
    """Referee the doubtful bars; the result's score and compare have the accepted rulings applied."""
    started = time.monotonic()
    try:
        settings = _settings_or_none()
        skip = _skip_reason(compare, settings)
        if skip is not None:
            logger.info("Score referee skipped: %s", skip)
            return RefereeResult(score, compare, _report("skipped", skip, [], None, started))
        return _referee(score, reading, compare, image_path, settings, trace, bar_boxes, agent_factory,
                        timeout_s, started)
    except Exception:
        logger.exception("Score referee crashed, so the readings are left as they were")
        return RefereeResult(score, compare, _report("failed", "model_error", [], None, started))


def _referee(score, reading, compare, image_path, settings: Settings, trace, bar_boxes, agent_factory, timeout_s,
             started: float) -> RefereeResult:
    session = RefereeSession(score, reading, compare, image_path, trace, bar_boxes)
    cancel = threading.Event()
    status, reason = "done", None
    try:
        agent_run = agent_factory(settings, session, timeout_s)
        _run_with_timeout(agent_run, cancel, timeout_s)
    except TimeoutError:
        logger.exception("Score referee timed out after %s s", timeout_s)
        status, reason = "failed", "timeout"
        session.close()  # first stop taking rulings, so the cancelled thread cannot slip one in
        cancel.set()
    except Exception:
        logger.exception("Score referee's model call failed")
        status, reason = "failed", "model_error"
    made = session.close()
    if status == "failed" and not made:
        return RefereeResult(score, compare, _report(status, reason, [], settings.vision_model, started))
    new_score, new_compare, rulings = apply_rulings(score, compare, made, session.reader_bar)
    return RefereeResult(new_score, new_compare, _report(status, reason, rulings, settings.vision_model, started))
