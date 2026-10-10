"""POST /sessions/{id}/transposition: the user sets the transposition and every take is re-diagnosed."""
import logging

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field, StrictInt

from .. import store
from ..errors import AppError
from . import config
from .rerun import rerun_takes
from .transposition import make_transposition

logger = logging.getLogger("app.diagnosis")
router = APIRouter()


class TranspositionRequest(BaseModel):
    semitones: StrictInt = Field(ge=config.MIN_TRANSPOSITION_SEMITONES, le=config.MAX_TRANSPOSITION_SEMITONES)


@router.post("/sessions/{session_id}/transposition")
def set_transposition(session_id: str, body: TranspositionRequest, background: BackgroundTasks) -> dict:
    session = store.get(session_id)
    if session.score_status != "confirmed":
        raise AppError(409, "wrong_state", "Confirm your sheet music before changing the transposition.")
    transposition = make_transposition(body.semitones, config.SOURCE_USER)
    store.update(session_id, "transposition", transposition)
    take_ids = list(store.get(session_id).takes)
    background.add_task(rerun_takes, session_id, take_ids)
    logger.info("Session %s transposition set to %s; rerunning %d take(s)", session_id, body.semitones, len(take_ids))
    return {"transposition": transposition, "rerun_takes": take_ids}
