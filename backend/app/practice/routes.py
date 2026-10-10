"""Practice routes: an exercise with its state, the progress view, and the rep routes."""
from fastapi import APIRouter

from .progress import exercise_with_state
from .progress_view import build_progress_view
from .rep_routes import router as rep_router

router = APIRouter()
router.include_router(rep_router)


@router.get("/sessions/{session_id}/exercises/{exercise_id}")
def get_exercise(session_id: str, exercise_id: str) -> dict:
    exercise, state = exercise_with_state(session_id, exercise_id)
    return {"exercise": exercise, "state": state}


@router.get("/sessions/{session_id}/progress")
def get_progress(session_id: str) -> dict:
    return build_progress_view(session_id)
