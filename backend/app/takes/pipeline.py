"""Background take pipeline: one run at a time per session. For now it only extracts audio."""
import logging
import threading

from .. import store
from .media_tools import MediaError, extract_wav, probe, wav_duration_s
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


def run_take_pipeline(session_id: str, take_id: str) -> None:
    """Process one take in a background thread; never raises, failures are recorded on the take."""
    with _lock_for(session_id):
        try:
            extract_audio(session_id, take_id)
            # TODO (pipeline-runner task): each step moves status forward; a failure sets status 'failed' + error.
            #   1. transcribe -> status 'transcribed'
            #   2. diagnosis.run -> status 'diagnosed'
            #   3. form.run for video takes (sets form_status), then status 'done'
        except MediaError as exc:
            logger.warning("Take %s/%s failed: %s (%s)", session_id, take_id, exc.code, exc)
            _fail(session_id, take_id, exc.code)
        except Exception:
            logger.exception("Take %s/%s pipeline crashed", session_id, take_id)
            try:
                _fail(session_id, take_id, "pipeline_error")
            except Exception:
                logger.exception("Could not record the failure of take %s/%s", session_id, take_id)
