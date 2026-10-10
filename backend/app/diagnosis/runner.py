"""diagnosis.run (steps 1-9 for one take) and diagnosis.rerank (steps 7-8 again, e.g. after form flags land)."""
import json
import logging

from .. import store
from ..errors import AppError
from ..takes.take_store import get_take, update_take
from . import config
from .rank import rank
from .saving import save_diagnosis
from .take_data import form_flags
from .timing import add_timing, save_clean_tempo
from .transposition import align_with_transposition

logger = logging.getLogger("app.diagnosis")

SCORE_FILE = "score.json"
STATUS_DIAGNOSED = "diagnosed"
STATUS_FAILED = "failed"
SETTLED_STATUSES = (STATUS_DIAGNOSED, "done")  # a re-run keeps these
NOT_TRANSCRIBED_STATUSES = ("processing", STATUS_FAILED)
DIAGNOSIS_KEYS = (
    "latency_ms", "grid", "played_bpm", "target_bpm", "alignment_quality", "cant_tell", "cant_tell_reason",
    "error_rate", "notes", "extras", "outside_count", "tuning_cents", "bars",
)
MS_PER_S = 1000


class ScoreMissing(Exception):
    """The session has no confirmed score to diagnose against."""


def _load_score(session, session_id: str) -> dict:
    path = store.session_dir(session_id) / SCORE_FILE
    if session.score_status != "confirmed" or not path.is_file():
        raise ScoreMissing(f"session {session_id} has no confirmed score")
    return json.loads(path.read_text(encoding="utf-8"))


def _analyse(session_id: str, take: dict) -> dict:
    """Steps 1-8 for one take; also saves the session's transposition and clean tempo when they apply."""
    session = store.get(session_id)
    score = _load_score(session, session_id)
    latency_ms = (session.calibration or {}).get("latency_ms") or 0
    take_input = {**take, "latency_s": latency_ms / MS_PER_S}
    played = take["notes"]
    transposition, aligned = align_with_transposition(score, played, take_input, session.instrument, session.transposition)
    timed = add_timing(aligned, played, take_input)
    diagnosis = {"transposition": transposition, **{key: timed[key] for key in DIAGNOSIS_KEYS}}
    diagnosis.update(rank(take["take_id"], diagnosis, form_flags(take)))
    if not diagnosis["cant_tell"]:
        if session.transposition is None:
            store.update(session_id, "transposition", transposition)
        save_clean_tempo(session_id, take_input, diagnosis)
    return diagnosis


def _record_failure(session_id: str, take_id: str, code: str) -> None:
    try:
        update_take(session_id, take_id, status=STATUS_FAILED, error=code)
    except Exception:
        logger.exception("Could not record that take %s/%s failed (%s)", session_id, take_id, code)


def _failure_code(error: Exception) -> str:
    if isinstance(error, ScoreMissing):
        return config.ERROR_NO_SCORE
    if isinstance(error, AppError) and error.code == config.ERROR_STORAGE:
        return config.ERROR_STORAGE
    return config.ERROR_DIAGNOSIS_FAILED


def run(session_id: str, take_id: str) -> None:
    """Diagnose a take and save the result; a failure is logged and recorded on the take, never raised.

    Raises only for an unknown session or take. A take that never reached transcription is skipped.
    """
    take = get_take(session_id, take_id)
    if take["status"] in NOT_TRANSCRIBED_STATUSES and not take["notes"]:
        logger.info("Skipped diagnosis of take %s/%s: it has no transcription", session_id, take_id)
        return
    try:
        diagnosis = _analyse(session_id, take)
        status = take["status"] if take["status"] in SETTLED_STATUSES else STATUS_DIAGNOSED
        save_diagnosis(session_id, take_id, diagnosis, status=status, error=None)
    except Exception as error:
        code = _failure_code(error)
        if code == config.ERROR_NO_SCORE:
            logger.warning("Take %s/%s can't be diagnosed: %s", session_id, take_id, error)
        else:
            logger.exception("Diagnosis of take %s/%s failed (%s)", session_id, take_id, code)
        _record_failure(session_id, take_id, code)


def rerank(session_id: str, take_id: str) -> None:
    """Redo steps 7-8 with the saved results and the take's current form flags (problem ids may change).

    Does nothing before the take is diagnosed or when the diagnosis is can't-tell.
    """
    take = get_take(session_id, take_id)
    diagnosis = take.get("diagnosis")
    if not diagnosis or diagnosis["cant_tell"]:
        logger.info("Skipped rerank of take %s/%s: nothing ranked to update", session_id, take_id)
        return
    save_diagnosis(session_id, take_id, {**diagnosis, **rank(take_id, diagnosis, form_flags(take))})
