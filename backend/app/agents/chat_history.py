"""The chat so far, as the Instructor sees it: only the turns its own coach style wrote.

A reply written by another coach style is never shown to the model, not even as labelled background: the new coach
copies it ("Then play bars...") instead of answering from its own focus. An exchange with another coach (the learner's
question and that coach's reply) is dropped whole, so each coach answers from the take data and its own earlier turns.
"""
from app.agents.personas import STANDARD_ID
from app.store import DEFAULT_PERSONA

HISTORY_TURNS = 10
USER_ROLE = "user"


def _written_in(turn: dict) -> str:
    """The coach style a turn's reply was written in; turns from before personas were Standard."""
    return turn.get("persona") or STANDARD_ID


def _own_turns(turns: list[dict], persona_id: str) -> list[dict]:
    """The recent turns without other coaches' exchanges (their replies and the questions those replies answered)."""
    own: list[dict] = []
    for turn in turns[-HISTORY_TURNS:]:
        if turn["role"] == USER_ROLE or _written_in(turn) == persona_id:
            own.append(turn)
        elif own and own[-1]["role"] == USER_ROLE:
            own.pop()
    return own


def history_messages(turns: list[dict], persona_id: str = DEFAULT_PERSONA) -> list[dict]:
    """The recent turns written in this coach style as plain text model messages, starting with a learner's message."""
    recent = [{"role": "user" if t["role"] == USER_ROLE else "assistant", "content": [{"text": t["text"]}]}
              for t in _own_turns(turns, persona_id)]
    while recent and recent[0]["role"] != "user":
        recent.pop(0)
    return recent
