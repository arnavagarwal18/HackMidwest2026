"""Answer one chat message: the Instructor under a time limit, or the measured sentences when it can't."""
import asyncio
import logging
from dataclasses import dataclass, field

from app import store
from app.agents import ai_run, run
from app.agents.credentials import CREDENTIALS_EXPIRED_LINE, is_credential_error
from app.agents.fallback import tier1_sentences
from app.agents.holder import ReplyHolder
from app.agents.hooks import CHAT_SUBMIT
from app.agents.chat_history import history_messages
from app.agents.instructor import build_instructor_agent, make_chat_tools
from app.agents.persona_run import PersonaRun, resolve_persona
from app.agents.submit_retry import invoke_until_submitted
from app.agents.trace import Trace

log = logging.getLogger(__name__)

FALLBACK_INTRO = "The AI instructor is unavailable right now. Here is what was measured:"
NO_TAKE_TEXT = "Record a take first."


@dataclass
class Reply:
    """An instructor reply: its text, the sentences it is made of, what the Checker dropped, and how it was made."""

    sentences: list[dict]
    mode: str  # 'ai' or 'fallback'
    text: str
    dropped: list[dict] = field(default_factory=list)
    fallback_reason: str | None = None


def _fallback(take: dict | None, reason: str, trace: Trace) -> Reply:
    log.warning("The instructor replies in fallback mode (%s)", reason)
    trace.add("instructor", "fallback", reason)
    if take is None:
        return Reply([], "fallback", NO_TAKE_TEXT, fallback_reason=reason)
    sentences = tier1_sentences(take.get("diagnosis") or {})
    return Reply(sentences, "fallback", " ".join([FALLBACK_INTRO, *[s["text"] for s in sentences]]), fallback_reason=reason)


async def _ask(session_id: str, take: dict, turns: list[dict], message: str, holder: ReplyHolder, trace: Trace) -> None:
    """One Instructor turn, in the coach style the session has now (read at reply time)."""
    session = store.get(session_id)
    ctx, tools = ai_run.context_and_tools(session_id, take, run.earlier_takes(session.takes, take))
    persona = resolve_persona(session.persona, trace, "instructor")
    agent = build_instructor_agent(ai_run.new_model(), {**tools, **make_chat_tools(session_id, take)}, ctx, holder, trace,
                                   history_messages(turns, persona.id), PersonaRun(persona))
    await asyncio.wait_for(
        invoke_until_submitted(agent, message, agent_name="instructor", tool_name=CHAT_SUBMIT.tool_name,
                               accepted=lambda: holder.reply is not None, trace=trace),
        ai_run.TIME_LIMIT_S)


def _failure_reason(holder: ReplyHolder, failure: BaseException | None) -> str:
    if isinstance(failure, asyncio.TimeoutError):
        return "timeout"
    return "model_error" if failure is not None or holder.tries == 0 else "checker_rejected"


def _ai_enabled(trace: Trace) -> bool:
    try:
        return run.ai_enabled()
    except Exception:
        log.exception("Could not read the AI settings; the instructor is unavailable")
        trace.add("instructor", "error", "settings", "AI settings could not be read")
        return False


def _record_failure(session_id: str, take: dict, exc: Exception, trace: Trace) -> None:
    """Log and trace why the Instructor failed. Only the error's class is kept: for credentials its message could hold secrets."""
    if is_credential_error(exc):
        log.error("The instructor failed for session %s take %s (%s)", session_id, take["take_id"], type(exc).__name__)
        log.warning(CREDENTIALS_EXPIRED_LINE)
    else:
        log.exception("The instructor failed for session %s take %s (%s)", session_id, take["take_id"], type(exc).__name__)
    trace.add("instructor", "error", type(exc).__name__)


def answer(session_id: str, take: dict | None, turns: list[dict], message: str, trace: Trace) -> Reply:
    """The instructor's reply to `message` about `take`, given the chat so far. Never raises: any failure gives the fallback reply."""
    if take is None:
        return _fallback(None, "no_take", trace)
    if not isinstance(take.get("diagnosis"), dict):
        return _fallback(take, "no_diagnosis", trace)
    if not _ai_enabled(trace):
        return _fallback(take, "disabled", trace)
    holder, failure = ReplyHolder(), None
    try:
        asyncio.run(_ask(session_id, take, turns, message, holder, trace))
    except Exception as exc:
        failure = exc
        _record_failure(session_id, take, exc, trace)
    if holder.reply is None:
        return _fallback(take, _failure_reason(holder, failure), trace)
    sentences = [ai_run.shown_sentence(s) for s in holder.reply["sentences"]]
    return Reply(sentences, "ai", " ".join(s["text"] for s in sentences), holder.dropped)
