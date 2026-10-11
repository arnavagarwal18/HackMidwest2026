"""form.run: track a video take, judge its posture, put the flags on bars, save take.form, then re-rank the diagnosis."""
import logging

from .. import store
from ..takes.pipeline_steps import resolve_step
from ..takes.take_store import update_take
from . import config
from .errors import FormError, FormFailed, FormUnavailable, TrackingPoor
from .link import add_bars_and_links, read_bar_spans
from .rules import analyse
from .saving import save_form
from .track import TrackResult, track_take
from .view import FRONT

logger = logging.getLogger("app.form")

STATUS_PROCESSING, STATUS_DONE, STATUS_FAILED = "processing", "done", "failed"


def _tracking_summary(result: TrackResult) -> dict:
    return {
        "fps_sampled": result.fps,
        "frames_total": result.frames_total,
        "frames_tracked": result.frames_tracked,
        "tracking_quality": round(result.tracking_quality, 3),
    }


def _failed_form(error: type[FormError]) -> dict:
    """take.form for a run that got no usable result."""
    return {"fps_sampled": None, "frames_total": 0, "frames_tracked": 0, "tracking_quality": 0.0, "view": FRONT, "view_ratio": None,
            "baseline": None, "rules_skipped": [], "flags": [], "error": error.as_dict()}


def _analysed_form(session_id: str, take_id: str) -> dict:
    """Track the take's video and judge it; raises FormError (video_unreadable, form_unavailable) or anything unexpected."""
    session = store.get(session_id)
    take = session.takes[take_id]
    result = track_take(session_id, take_id)
    form = {**_tracking_summary(result), "view": FRONT, "view_ratio": None, "baseline": None, "rules_skipped": [], "flags": [], "error": None}
    if result.tracking_quality < config.TRACKING_QUALITY_MIN:
        form["error"] = TrackingPoor.as_dict()
    else:
        analysis = analyse(result.frames, session.instrument, take_id, result.width, result.height)
        spans = read_bar_spans(session_id, take["bar_from"], take["bar_to"])
        form.update(view=analysis["view"], view_ratio=analysis["view_ratio"], baseline=analysis["baseline"], rules_skipped=analysis["rules_skipped"],
                    flags=add_bars_and_links(analysis["flags"], take.get("diagnosis"), spans))
    if result.warning:
        form["warning"] = result.warning
    return form


def _checked_form(session_id: str, take_id: str) -> dict:
    """take.form for the take, with any failure turned into its `error`; never raises."""
    try:
        return _analysed_form(session_id, take_id)
    except FormUnavailable as error:  # the tracker already logged why, once
        logger.info("Form check of take %s/%s skipped: %s", session_id, take_id, error)
        return _failed_form(type(error))
    except FormError as error:
        logger.warning("Form check of take %s/%s failed: %s (%s)", session_id, take_id, error.code, error)
        return _failed_form(type(error))
    except Exception:
        logger.exception("Form check of take %s/%s failed", session_id, take_id)
        return _failed_form(FormFailed)


def _rerank(session_id: str, take_id: str) -> None:
    """Ask note diagnosis to rank again with the new flags; skipped with a warning when it can't."""
    try:
        rerank = resolve_step("app.diagnosis", "rerank")
        if rerank:
            rerank(session_id, take_id)
    except Exception:
        logger.exception("Re-ranking take %s/%s after the form check failed", session_id, take_id)


def _record_failure(session_id: str, take_id: str) -> None:
    try:
        update_take(session_id, take_id, form=_failed_form(FormFailed), form_status=STATUS_FAILED)
    except Exception:
        logger.exception("Could not record that the form check of take %s/%s failed", session_id, take_id)


def run(session_id: str, take_id: str) -> None:
    """Form check of a video take, saved as take.form; every failure is logged and recorded there, never raised."""
    try:
        update_take(session_id, take_id, form_status=STATUS_PROCESSING)
        form = _checked_form(session_id, take_id)
        save_form(session_id, take_id, form, STATUS_FAILED if form["error"] else STATUS_DONE)
    except Exception:
        logger.exception("Could not save the form check of take %s/%s", session_id, take_id)
        _record_failure(session_id, take_id)
    _rerank(session_id, take_id)
