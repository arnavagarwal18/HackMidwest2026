"""FastAPI app: session routes, shared error handling, static frontend at /."""
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import store
from .diagnosis.analysis_routes import router as analysis_router
from .diagnosis.routes import router as diagnosis_router
from .errors import register_error_handlers
from .form.routes import router as form_router
from .lan import router as lan_router
from .practice.routes import router as practice_router
from .score.photo_routes import router as photo_router
from .score.routes import router as score_router
from .takes.calibration_routes import router as calibration_router
from .agents.chat_routes import router as chat_router
from .agents.persona_routes import router as persona_router
from .agents.personas import STANDARD_ID, require_known
from .agents.routes import router as feedback_router
from .agents.trace_routes import router as trace_router
from .takes.routes import router as takes_router
from .tone_page import router as tone_router

logging.basicConfig(level=logging.INFO)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

app = FastAPI(title="Practice Coach")
register_error_handlers(app)
app.include_router(takes_router)
app.include_router(score_router)
app.include_router(photo_router)
app.include_router(calibration_router)
app.include_router(diagnosis_router)
app.include_router(feedback_router)
app.include_router(trace_router)
app.include_router(chat_router)
app.include_router(persona_router)
app.include_router(analysis_router)
app.include_router(form_router)
app.include_router(practice_router)
app.include_router(lan_router)
app.include_router(tone_router)


class CreateSession(BaseModel):
    instrument: Literal["violin", "trumpet"]
    persona: str | None = None  # a coach style id; left out means Standard


@app.post("/sessions", status_code=201)
def create_session(body: CreateSession) -> dict:
    session = store.create(body.instrument, require_known(body.persona) if body.persona is not None else STANDARD_ID)
    return {"session_id": session.session_id, "instrument": session.instrument, "persona": session.persona}


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = store.get(session_id)
    return {
        "session_id": session.session_id,
        "instrument": session.instrument,
        "persona": session.persona,
        "score_status": session.score_status,
        "has_calibration": session.calibration is not None,
        "take_ids": list(session.takes),
    }


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
