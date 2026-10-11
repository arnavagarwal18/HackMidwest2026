"""Step 2: which transposition to line a take up with (the user's if set, else searched when a take needs it)."""
import logging

from .. import store
from . import config
from .take_alignment import align_take

logger = logging.getLogger("app.diagnosis")


def make_transposition(semitones: int, source: str) -> dict:
    return {"semitones": semitones, "source": source}


def base_transposition(score: dict, instrument: str) -> dict:
    """The score file's written transposition if it has one, else the instrument's default."""
    written = score.get("written_transpose_semitones")
    if written is not None:
        return make_transposition(written, config.SOURCE_FILE)
    default = config.INSTRUMENT_DEFAULT_TRANSPOSITION.get(instrument, 0)
    return make_transposition(default, config.SOURCE_DEFAULT)


def _candidates(base_semitones: int) -> list[int]:
    """Every offset in the search range, nearest the base first (ties go to the lower offset)."""
    offsets = range(config.MIN_TRANSPOSITION_SEMITONES, config.MAX_TRANSPOSITION_SEMITONES + 1)
    return sorted({base_semitones, *offsets}, key=lambda s: (abs(s - base_semitones), s))


def _cannot_be_beaten(base_quality: float) -> bool:
    """True when no candidate could line up at least DETECTION_MIN_GAIN better (quality tops out at 1)."""
    return base_quality + config.DETECTION_MIN_GAIN - config.DETECTION_EPSILON > config.MAX_ALIGNMENT_QUALITY


def detect_transposition(score: dict, played: list[dict], take: dict, base: dict) -> tuple[dict, dict]:
    """Try every offset; keep `base` unless another lines up at least DETECTION_MIN_GAIN better.

    The played notes are already transcribed, so each candidate only repeats steps 3-4. Ties go to the
    offset nearest the base. Returns (transposition, alignment of the take with that transposition).
    """
    base_result = align_take(score, played, take, base["semitones"])
    base_quality = base_result["score_quality"]
    if _cannot_be_beaten(base_quality):
        return base, base_result
    best, best_result = base["semitones"], base_result
    for semitones in _candidates(base["semitones"])[1:]:
        result = align_take(score, played, take, semitones)
        if result["score_quality"] > best_result["score_quality"]:
            best, best_result = semitones, result
    gain = best_result["score_quality"] - base_quality
    if best == base["semitones"] or gain < config.DETECTION_MIN_GAIN - config.DETECTION_EPSILON:
        return base, base_result
    logger.info("Transposition switched from %s to %s (line-up quality over the score +%.2f)", base["semitones"], best, gain)
    return make_transposition(best, config.SOURCE_DETECTED), best_result


def _is_low_match(alignment: dict) -> bool:
    """Low match over the played bars, or over the whole score (a wrong transposition can fit a few bars by chance)."""
    low_in_played_bars = alignment["cant_tell"] and alignment["cant_tell_reason"] == config.CANT_TELL_LOW_MATCH
    return low_in_played_bars or alignment["score_quality"] < config.MIN_ALIGNMENT_QUALITY


def align_with_transposition(
    score: dict, played: list[dict], take: dict, instrument: str, current: dict | None
) -> tuple[dict, dict]:
    """Line a take up using the session's transposition, searching for a better one when that's due.

    A transposition the user set is used as is and never searched. Otherwise the search runs on the
    session's first diagnosed take (`current` is None) and on any later take that comes back can't tell
    with `low_match`. Returns (transposition, alignment); `remember_transposition` saves it on the session.
    """
    base = base_transposition(score, instrument)
    if current is None:
        return detect_transposition(score, played, take, base)
    alignment = align_take(score, played, take, current["semitones"])
    if current["source"] == config.SOURCE_USER or not _is_low_match(alignment):
        return current, alignment
    return detect_transposition(score, played, take, base)


def remember_transposition(session_id: str, session, transposition: dict, alignment: dict) -> None:
    """Save the transposition a take was lined up with on the session when it's new.

    A take that can't be told with the file/default base doesn't change the session; a detected one does.
    """
    if transposition == session.transposition:
        return
    if alignment["cant_tell"] and transposition["source"] != config.SOURCE_DETECTED:
        return
    store.update(session_id, "transposition", transposition)
