"""Chat routes: ask the Instructor about a take, or read the conversation so far."""
import threading
import time
from contextlib import contextmanager

from fastapi import APIRouter
from pydantic import BaseModel

from app import store
from app.agents.chat_run import answer
from app.agents.chat_store import append_turn, load_turns, new_turn
from app.agents.trace import Trace
from app.errors import AppError

router = APIRouter()

MESSAGE_MAX_CHARS = 1000
_reply_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


class ChatRequest(BaseModel):
    message: str
    take_id: str | None = None


@contextmanager
def _one_reply_at_a_time(session_id: str):
    """One Instructor reply per session at a time; other sessions are not held up."""
    with _registry_lock:
        lock = _reply_locks.setdefault(session_id, threading.Lock())
    if not lock.acquire(blocking=False):
        raise AppError(409, "wrong_state", "Instructor is already replying.")
    try:
        yield
    finally:
        lock.release()


def _valid_message(message: str) -> str:
    text = message.strip()
    if not 1 <= len(text) <= MESSAGE_MAX_CHARS:
        raise AppError(422, "bad_request", f"Write a message of 1 to {MESSAGE_MAX_CHARS} characters.")
    return text


def _chosen_take(takes: dict[str, dict], take_id: str | None) -> dict | None:
    """The asked-for take, else the latest take that is done (None when there is none)."""
    if take_id is not None:
        if take_id not in takes:
            raise AppError(404, "take_not_found", "We couldn't find that take.")
        return takes[take_id]
    done = [t for t in takes.values() if t.get("status") == "done"]
    return max(done, key=lambda t: int(t["take_id"][1:]), default=None)


@router.post("/sessions/{session_id}/chat")
def post_chat(session_id: str, body: ChatRequest) -> dict:
    session = store.get(session_id)
    message = _valid_message(body.message)
    take = _chosen_take(session.takes, body.take_id)
    take_id = take["take_id"] if take else None
    with _one_reply_at_a_time(session_id):
        started, trace = time.monotonic(), Trace()
        turns = load_turns(session_id)
        user_turn = new_turn(turns, "user", message, take_id)
        append_turn(session_id, user_turn)
        reply = answer(session_id, take, turns, message, trace)
        instructor_turn = new_turn([*turns, user_turn], "instructor", reply.text, take_id, mode=reply.mode,
                                   fallback_reason=reply.fallback_reason, sentences=reply.sentences, dropped=reply.dropped,
                                   duration_ms=round((time.monotonic() - started) * 1000))
        append_turn(session_id, instructor_turn)
        trace.save(store.session_dir(session_id) / f"{instructor_turn['id']}_trace.json")
    return {"user_turn": user_turn, "instructor_turn": instructor_turn}


@router.get("/sessions/{session_id}/chat")
def get_chat(session_id: str) -> dict:
    store.get(session_id)
    return {"turns": load_turns(session_id)}
