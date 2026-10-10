"""Step 2: which transposition to line a take up with (locked per session after the first take)."""
import logging

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
    return list(dict.fromkeys([base_semitones, *config.DETECTION_CANDIDATES]))


def detect_transposition(score: dict, played: list[dict], take: dict, base: dict) -> tuple[dict, dict]:
    """Try each candidate; keep `base` unless another lines up at least DETECTION_MIN_GAIN better.

    Returns (transposition, alignment of the take with that transposition).
    """
    results = {s: align_take(score, played, take, s) for s in _candidates(base["semitones"])}
    base_result = results[base["semitones"]]
    best = max(results, key=lambda s: results[s]["alignment_quality"])  # first wins ties, so base is preferred
    gain = results[best]["alignment_quality"] - base_result["alignment_quality"]
    if best == base["semitones"] or gain < config.DETECTION_MIN_GAIN - config.DETECTION_EPSILON:
        return base, base_result
    logger.info("Transposition switched from %s to %s (line-up quality +%.2f)", base["semitones"], best, gain)
    return make_transposition(best, config.SOURCE_DETECTED), results[best]


def align_with_transposition(
    score: dict, played: list[dict], take: dict, instrument: str, locked: dict | None
) -> tuple[dict, dict]:
    """Line a take up using the session's transposition, choosing one first if none is locked yet.

    Returns (transposition, alignment). The caller saves the transposition on the session when
    `locked` was None (the session's first diagnosed take); later takes pass it back in unchanged.
    """
    if locked is not None:
        return locked, align_take(score, played, take, locked["semitones"])
    return detect_transposition(score, played, take, base_transposition(score, instrument))
