"""Background take pipeline, one run at a time per session: extract audio, transcribe, diagnose, the form check for videos, then feedback."""
import logging
import threading

from .. import store
from .media_tools import MediaError, extract_wav, probe, wav_duration_s
from .pipeline_steps import Step, StepFailed, resolve_step, transcribe_take
from .take_store import update_take

logger = logging.getLogger("app.takes.pipeline")

MAX_DURATION_S = 180

_pipeline_locks: dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()


def _lock_for(session_id: str) -> threading.Lock:
    with _registry_lock:
        return _pipeline_locks.setdefault(session_id, threading.Lock())


def start_pipeline(session_id: str, take_id: str) -> threading.Thread:
    thread = threading.Thread(target=run_take_pipeline, args=(session_id, take_id), name=f"take-{take_id}", daemon=True)
    thread.start()
    return thread


def _fail(session_id: str, take_id: str, code: str) -> None:
    update_take(session_id, take_id, status="failed", error=code)


def extract_audio(session_id: str, take_id: str) -> None:
    """Write {take_id}.wav and set duration_s; raises MediaError carrying the error code to store."""
    folder = store.session_dir(session_id)
    take = store.get(session_id).takes[take_id]
    info = probe(folder / take["file"])
    if not info.has_audio:
        raise MediaError("no_audio_track", "the file has no audio stream")
    if info.duration_s is not None and info.duration_s > MAX_DURATION_S:
        raise MediaError("too_long", f"the file is {info.duration_s:.1f} s long")
    extract_wav(folder / take["file"], folder / take["audio"])
    duration = info.duration_s if info.duration_s is not None else wav_duration_s(folder / take["audio"])
    if duration > MAX_DURATION_S:
        raise MediaError("too_long", f"the file is {duration:.1f} s long")
    update_take(session_id, take_id, duration_s=round(duration, 3))


def _diagnose(session_id: str, take_id: str, run: Step | None) -> None:
    run = run or resolve_step("app.diagnosis")
    try:
        if run:
            run(session_id, take_id)
    except Exception:
        logger.exception("Diagnosis of take %s/%s failed", session_id, take_id)
        raise StepFailed("diagnosis_failed")
    recorded = store.get(session_id).takes[take_id]
    if recorded["status"] == "failed":  # diagnosis.run records its own failures (no_score, storage_error, ...)
        raise StepFailed(recorded["error"])
    update_take(session_id, take_id, status="diagnosed")


def _check_form(session_id: str, take_id: str, run: Step | None) -> None:
    """Video takes only; a failure here is recorded as form_status 'failed' and never fails the take."""
    run = run or resolve_step("app.form")
    if run is None:
        return
    update_take(session_id, take_id, form_status="processing")
    try:
        run(session_id, take_id)
        if store.get(session_id).takes[take_id]["form_status"] == "processing":  # app.form.run records its own outcome
            update_take(session_id, take_id, form_status="done")
    except Exception:
        logger.exception("Form check of take %s/%s failed", session_id, take_id)
        update_take(session_id, take_id, form_status="failed")


def _give_feedback(session_id: str, take_id: str, run: Step | None) -> None:
    """Feedback for a practice take (not for other purposes); run_feedback handles its own failures."""
    if store.get(session_id).takes[take_id].get("purpose", "take") != "take":
        return
    run = run or resolve_step("app.agents.run", "run_feedback")
    if run:
        run(session_id, take_id)


def run_take_pipeline(session_id: str, take_id: str, *, transcriber=None, diagnose: Step | None = None,
                      check_form: Step | None = None, give_feedback: Step | None = None) -> None:
    """Process one take in a background thread; never raises, failures are recorded on the take.

    The keyword arguments replace the transcriber and the LLD-3 / LLD-4 / LLD-5 steps (tests); by default the steps
    are looked up as app.diagnosis.run, app.form.run and app.agents.run.run_feedback when needed, and skipped
    while they don't exist.
    """
    with _lock_for(session_id):
        try:
            extract_audio(session_id, take_id)
            transcribe_take(session_id, take_id, transcriber)
            _diagnose(session_id, take_id, diagnose)
            if store.get(session_id).takes[take_id]["kind"] == "video":
                _check_form(session_id, take_id, check_form)
            _give_feedback(session_id, take_id, give_feedback)
            if store.get(session_id).takes[take_id]["status"] != "failed":  # run_feedback marks the take failed if it can't save
                update_take(session_id, take_id, status="done")
        except (MediaError, StepFailed) as exc:
            logger.warning("Take %s/%s failed: %s (%s)", session_id, take_id, exc.code, exc)
            _fail(session_id, take_id, exc.code)
        except Exception:
            logger.exception("Take %s/%s pipeline crashed", session_id, take_id)
            try:
                _fail(session_id, take_id, "pipeline_error")
            except Exception:
                logger.exception("Could not record the failure of take %s/%s", session_id, take_id)
