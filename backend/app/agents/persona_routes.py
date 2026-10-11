"""Coach-style routes: list the personas on offer, and change a session's persona."""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app import store
from app.agents.personas import PERSONAS, STANDARD_ID, Persona, require_known

log = logging.getLogger(__name__)
router = APIRouter()


class PickPersona(BaseModel):
    persona: str


def persona_view(persona: Persona) -> dict:
    return {"id": persona.id, "label": persona.label, "hint": persona.hint,
            "tempo": {"kind": persona.tempo.kind, "value": persona.tempo.value}}


@router.get("/personas")
def list_personas() -> dict:
    return {"personas": [persona_view(persona) for persona in PERSONAS], "default": STANDARD_ID}


@router.patch("/sessions/{session_id}")
def pick_persona(session_id: str, body: PickPersona) -> dict:
    """Change the coach style for later feedback and chat replies; work already done keeps the style it was made in."""
    session = store.get(session_id)  # 404 session_not_found
    persona_id = require_known(body.persona)
    store.update(session_id, "persona", persona_id)
    log.info("Session %s coach style changed from %s to %s", session_id, session.persona, persona_id)
    return {"session_id": session_id, "persona": persona_id}
