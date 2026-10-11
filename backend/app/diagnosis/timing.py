"""Step 5 (timing, drift per bar) and step 6 (error rate, clean tempo) of note diagnosis."""
import logging
from collections import Counter
from statistics import median

from .. import store
from . import config
from .align import fit_line
from .errors import input_error

logger = logging.getLogger("app.diagnosis")

SECONDS_PER_MINUTE = 60.0


def timing_flag(timing_ms: float | None) -> str | None:
    """'late' beyond +80 ms, 'early' beyond -80 ms, else None."""
    if timing_ms is None:
        return None
    if timing_ms > config.LATE_EARLY_MS:
        return config.TIMING_LATE
    if timing_ms < -config.LATE_EARLY_MS:
        return config.TIMING_EARLY
    return None


def drift_label(drift_pct: float | None) -> str | None:
    if drift_pct is None:
        return None
    if drift_pct > config.DRIFT_LIMIT_PCT:
        return config.DRIFT_RUSHING
    if drift_pct < -config.DRIFT_LIMIT_PCT:
        return config.DRIFT_DRAGGING
    return config.DRIFT_STEADY


def error_rate(notes: list[dict]) -> float | None:
    """(wrong + missed + late + early) / expected; uncertain and not-played notes count on neither side.

    None when no expected note is left to judge.
    """
    judged = [note for note in notes if note["status"] not in config.UNJUDGED_STATUSES]
    if not judged:
        return None
    errors = sum(1 for note in judged if note["status"] in (config.STATUS_WRONG, config.STATUS_MISSED))
    errors += sum(1 for note in judged if timing_flag(note["timing_ms"]) is not None)
    return errors / len(judged)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, config.TIMING_DECIMALS)


def _time_notes(
    notes: list[dict], onset_by_i: dict[int, float], grid: dict, latency_s: float
) -> tuple[list[dict], dict[int, list[tuple[float, float]]]]:
    """Notes with timing_ms filled in, and per bar the (expected beat, played onset) of its ok notes.

    Only a metronome grid leaves the calibration latency in the played onsets; a fitted grid already
    contains it, so no latency is subtracted there.
    """
    latency_s = latency_s if grid["kind"] == config.GRID_METRONOME else 0.0
    timed = []
    ok_points: dict[int, list[tuple[float, float]]] = {}
    for note in notes:
        timing_ms = None
        if note["status"] in config.TIMED_STATUSES:
            onset_s = onset_by_i[note["played_i"]]
            timing_ms = (onset_s - latency_s - note["expected_onset_s"]) * config.MS_PER_S
            if note["status"] == config.STATUS_OK:
                beat = (note["expected_onset_s"] - grid["offset_s"]) / grid["sec_per_beat"]
                ok_points.setdefault(note["bar"], []).append((beat, onset_s))
        timed.append({**note, "timing_ms": _round(timing_ms)})
    return timed, ok_points


def _local_bpm(points: list[tuple[float, float]]) -> float | None:
    line = fit_line(points, config.MIN_BAR_NOTES_FOR_TEMPO)
    return None if line is None else SECONDS_PER_MINUTE / line.sec_per_beat


def _local_bpms(ok_points: dict[int, list[tuple[float, float]]], bar_from: int, bar_to: int) -> dict[int, float | None]:
    """Per bar: the tempo through its ok notes plus the first ok note of the next bar (None below 2 points)."""
    bpms = {}
    for bar in range(bar_from, bar_to + 1):
        following = ok_points.get(bar + 1, [])[:1]
        bpms[bar] = _local_bpm(ok_points.get(bar, []) + following)
    return bpms


def _bar_result(
    take_id: str, bar: int, notes: list[dict], extras: list[dict], local_bpm: float | None, reference_bpm: float | None
) -> dict:
    in_bar = [note for note in notes if note["bar"] == bar and note["status"] != config.STATUS_NOT_PLAYED]
    counts = Counter(note["status"] for note in in_bar)
    timings = [note["timing_ms"] for note in in_bar if note["timing_ms"] is not None]
    drift_pct = None if local_bpm is None else (local_bpm - reference_bpm) / reference_bpm * 100
    return {
        "id": f"b:{take_id}:{bar}",
        "bar": bar,
        "expected": len(in_bar),
        "ok": counts[config.STATUS_OK],
        "wrong": counts[config.STATUS_WRONG],
        "missed": counts[config.STATUS_MISSED],
        "extra": sum(1 for extra in extras if extra["bar"] == bar),
        "uncertain": counts[config.STATUS_UNCERTAIN],
        "mean_timing_ms": _round(sum(timings) / len(timings)) if timings else None,
        "local_bpm": _round(local_bpm),
        "drift_pct": _round(drift_pct),
        "drift": drift_label(drift_pct),
    }


def add_timing(result: dict, played: list[dict], take: dict) -> dict:
    """Add steps 5-6 to `align_take`'s result for the same played notes and take.

    Returns the result with timing_ms on each note plus `bars`, `played_bpm`, `target_bpm`, `tempo_vs_goal_pct`,
    `reference_bpm` (the median of the bars' local tempos, None with none), `latency_ms` and `error_rate`.
    played_bpm comes from the step 3 fit; with no fit it is the grid's tempo. A bar's drift is against `reference_bpm`.
    """
    onset_by_i = {note["i"]: note["onset_s"] for note in played}
    missing = [i for note in result["notes"] if (i := note["played_i"]) is not None and i not in onset_by_i]
    if missing:
        raise input_error(f"Played notes {missing} are not in the played notes given to timing.")
    latency_s = take.get("latency_s") or 0.0
    notes, ok_points = _time_notes(result["notes"], onset_by_i, result["grid"], latency_s)
    sec_per_beat = (result["fit"] or result["grid"])["sec_per_beat"]
    local_bpms = _local_bpms(ok_points, take["bar_from"], take["bar_to"])
    known = [bpm for bpm in local_bpms.values() if bpm is not None]
    reference_bpm = median(known) if known else None
    bars = [
        _bar_result(take["take_id"], bar, notes, result["extras"], local_bpm, reference_bpm)
        for bar, local_bpm in local_bpms.items()
    ]
    played_bpm = SECONDS_PER_MINUTE / sec_per_beat
    timed = {
        **result,
        "notes": notes,
        "bars": bars,
        "played_bpm": _round(played_bpm),
        "target_bpm": take["tempo_bpm"],
        "tempo_vs_goal_pct": _round((played_bpm - take["tempo_bpm"]) / take["tempo_bpm"] * 100),
        "reference_bpm": _round(reference_bpm),
        "latency_ms": latency_s * config.MS_PER_S,
        "error_rate": error_rate(notes),
    }
    logger.info(
        "timing: take %s played_bpm %s error_rate %s", take["take_id"], timed["played_bpm"], timed["error_rate"]
    )
    return timed


def clean_tempo_key(bar_from: int, bar_to: int) -> str:
    return f"{bar_from}-{bar_to}"


def clean_tempo_for(takes: dict[str, dict], take: dict, diagnosis: dict) -> float:
    """Highest played_bpm among takes on this range with error_rate <= 0.10 and not can't tell.

    `take`/`diagnosis` are the take just diagnosed (its stored copy, if any, is ignored). With no such
    take the answer is 70% of this take's played_bpm.
    """
    candidates = [diagnosis] + [
        other["diagnosis"]
        for take_id, other in takes.items()
        if take_id != take["take_id"]
        and (other["bar_from"], other["bar_to"]) == (take["bar_from"], take["bar_to"])
        and other.get("diagnosis")
    ]
    clean = [
        d["played_bpm"]
        for d in candidates
        if not d.get("cant_tell") and d.get("error_rate") is not None and d["error_rate"] <= config.CLEAN_MAX_ERROR_RATE
    ]
    if clean:
        return max(clean)
    return _round(config.CLEAN_FALLBACK_FRACTION * diagnosis["played_bpm"])


def save_clean_tempo(session_id: str, take: dict, diagnosis: dict) -> float:
    """Work out the clean tempo for the take's bar range and save it to session.clean_tempo."""
    session = store.get(session_id)
    tempo = clean_tempo_for(session.takes, take, diagnosis)
    key = clean_tempo_key(take["bar_from"], take["bar_to"])
    store.update(session_id, "clean_tempo", {**session.clean_tempo, key: tempo})
    logger.info("clean tempo for session %s bars %s: %s BPM", session_id, key, tempo)
    return tempo
