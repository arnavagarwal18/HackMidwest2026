"""The chat so far, as the Instructor sees it: its own coach style's turns as history, other coaches' turns as labelled context.

A reply written by another coach style must never be handed to the model as its own earlier words, or the new coach
continues it ("Then play bars...") instead of answering from its own focus. Those exchanges (the learner's question and
that coach's reply) leave the message history and come back as a labelled note in the system prompt.
"""
import logging
from dataclasses import dataclass

from app.agents.personas import STANDARD_ID
from app.store import DEFAULT_PERSONA

log = logging.getLogger(__name__)

HISTORY_TURNS = 10
USER_ROLE = "user"
EARLIER_COACHES_INTRO = (
    "Earlier in this chat, other coach styles answered the learner. That is background only: those words are not yours, "
    "so never continue, repeat or build on them, and never begin with a word like Then, Also or Next. You are the "
    "{label} coach: answer the learner's new question yourself, from your own focus, even if it is the same question."
)
EARLIER_COACH_LINE = '- The learner asked: "{question}" The {label} coach said: "{reply}"'


@dataclass(frozen=True)
class OtherCoachExchange:
    """A question and the reply a different coach style gave to it."""

    coach_label: str
    question: str
    reply: str


def _written_in(turn: dict) -> str:
    """The coach style a turn's reply was written in; turns from before personas were Standard."""
    return turn.get("persona") or STANDARD_ID


def _label(persona_id: str) -> str:
    return persona_id.capitalize()


def _split_recent(turns: list[dict], persona_id: str) -> tuple[list[dict], list[OtherCoachExchange]]:
    """The recent turns without other coaches' exchanges, and those exchanges in order."""
    own: list[dict] = []
    others: list[OtherCoachExchange] = []
    for turn in turns[-HISTORY_TURNS:]:
        if turn["role"] == USER_ROLE or _written_in(turn) == persona_id:
            own.append(turn)
            continue
        question = own.pop() if own and own[-1]["role"] == USER_ROLE else None
        others.append(OtherCoachExchange(_label(_written_in(turn)), question["text"] if question else "", turn["text"]))
    return own, others


def history_messages(turns: list[dict], persona_id: str = DEFAULT_PERSONA) -> list[dict]:
    """The recent turns written in this coach style as plain text model messages, starting with a learner's message."""
    own, _ = _split_recent(turns, persona_id)
    recent = [{"role": "user" if t["role"] == USER_ROLE else "assistant", "content": [{"text": t["text"]}]} for t in own]
    while recent and recent[0]["role"] != "user":
        recent.pop(0)
    return recent


def with_earlier_coaches(base: str, turns: list[dict], persona_id: str, label: str) -> str:
    """The system prompt with a labelled note of what other coach styles said earlier added; `base` itself when there is none."""
    _, others = _split_recent(turns, persona_id)
    if not others:
        return base
    lines = [EARLIER_COACH_LINE.format(question=o.question, label=o.coach_label, reply=o.reply) for o in others]
    log.info("The %s coach gets %d earlier exchange(s) from other coach styles as labelled context", persona_id, len(others))
    return "\n".join([base, EARLIER_COACHES_INTRO.format(label=label), *lines, ""])
