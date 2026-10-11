"""Step 4: mark each expected note ok / wrong / uncertain / missed, collect Extras, judge the match."""
from statistics import median

from . import config
from .align import Pair
from .expected import ExpectedNote, midi_to_name


def _bar_at(bar_starts: list[tuple[int, float]], beat: float) -> int:
    """The bar containing `beat`; before the range counts as the first bar, after it as the last."""
    bar = bar_starts[0][0]
    for number, start in bar_starts:
        if beat >= start:
            bar = number
    return bar


def tuning_offset(expected: list[ExpectedNote], played: list[dict], pairs: list[Pair]) -> float:
    """The player's own tuning, in semitones: the median sharp/flat of their in-tune-ish pairs, clamped.

    Only pairs within OK_TOLERANCE_SEMITONES of the expected note count; with fewer than TUNING_MIN_PAIRS
    of them the offset is 0.
    """
    deviations = [
        played[p]["midi_float"] - expected[e].midi
        for e, p in pairs
        if abs(played[p]["midi_float"] - expected[e].midi) <= config.OK_TOLERANCE_SEMITONES
    ]
    if len(deviations) < config.TUNING_MIN_PAIRS:
        return 0.0
    return max(-config.TUNING_MAX_SEMITONES, min(config.TUNING_MAX_SEMITONES, median(deviations)))


def _deviation(played: dict, expected_midi: int, tuning: float) -> float:
    return played["midi_float"] - tuning - expected_midi


def _pair_status(deviation: float, confidence: float) -> str:
    if abs(deviation) <= config.OK_TOLERANCE_SEMITONES:
        return config.STATUS_OK
    if confidence < config.CONFIDENCE_THRESHOLD:
        return config.STATUS_UNCERTAIN
    return config.STATUS_WRONG


def _note_result(note: ExpectedNote, expected_onset_s: float, played: dict | None, tuning: float) -> dict:
    result = {
        "id": note.id,
        "bar": note.bar,
        "idx": note.idx,
        "expected_name": note.name,
        "expected_midi": note.midi,
        "expected_onset_s": expected_onset_s,
        "status": config.STATUS_MISSED,
        "played_i": None,
        "played_name": None,
        "played_midi_float": None,
        "cents_off": None,
        "timing_ms": None,
        "confidence": None,
    }
    if played is not None:
        deviation = _deviation(played, note.midi, tuning)
        result.update(
            status=_pair_status(deviation, played["confidence"]),
            played_i=played["i"],
            played_name=midi_to_name(played["midi"]),
            played_midi_float=played["midi_float"],
            cents_off=round(deviation * config.CENTS_PER_SEMITONE, 2),
            confidence=played["confidence"],
        )
    return result


def _extra(take_id: str, played: dict, bar: int) -> dict:
    return {
        "id": f"x:{take_id}:{played['i']}",
        "played_i": played["i"],
        "bar": bar,
        "onset_s": played["onset_s"],
        "played_name": midi_to_name(played["midi"]),
        "confidence": played["confidence"],
    }


def _outside_window(
    expected: list[ExpectedNote], played: list[dict], pairs: list[Pair], beat_s: float
) -> tuple[float, float] | None:
    """(earliest, latest) played onset still counted as inside the chosen bars; None with no pairs."""
    if not pairs:
        return None
    margin_s = config.OUTSIDE_MARGIN_BEATS * beat_s
    first_onset = min(played[p]["onset_s"] for _, p in pairs)
    last_expected, last_played = max(pairs, key=lambda pair: played[pair[1]]["onset_s"])
    last_end = played[last_played]["onset_s"] + expected[last_expected].dur_beats * beat_s
    return first_onset - margin_s, last_end + margin_s


def cant_tell_reason(expected_count: int, pair_count: int, quality: float) -> str | None:
    if expected_count < config.MIN_EXPECTED_NOTES:
        return config.CANT_TELL_TOO_SHORT
    if quality < config.MIN_ALIGNMENT_QUALITY:
        return config.CANT_TELL_LOW_MATCH
    if pair_count < config.MIN_PAIRED_FRACTION * expected_count:
        return config.CANT_TELL_FEW_PAIRS
    return None


def played_window(expected: list[ExpectedNote], pairs: list[Pair]) -> tuple[int, int] | None:
    """(first, last) bar that holds a paired expected note; None with no pairs."""
    bars = [expected[e].bar for e, _ in pairs]
    return (min(bars), max(bars)) if bars else None


def _not_played(result: dict) -> dict:
    return {**result, "status": config.STATUS_NOT_PLAYED}


def mark_alignment(
    take_id: str,
    expected: list[ExpectedNote],
    played: list[dict],
    pairs: list[Pair],
    grid: dict,
    bar_starts: list[tuple[int, float]],
    beat_s: float,
) -> dict:
    """Returns notes, extras, outside_count, tuning_cents, played_bars, not_played_count, alignment_quality, cant_tell
    and cant_tell_reason, plus `score_quality` (ok count over every expected note, for the transposition search).

    Expected notes in whole bars before the first or after the last bar holding a pair are 'not_played': never
    missed, and left out of the quality and can't-tell checks (`played_bars` is [first, last], None with no pairs).

    Notes are marked against the player's own tuning (see `tuning_offset`); cents_off is relative to it.

    `beat_s` is seconds per beat (the step 3 fit's, else from the target tempo). An unpaired played note
    far before the first pair or after the last pair's end is outside the range: counted, never an Extra.
    """
    tuning = tuning_offset(expected, played, pairs)
    partner = {e: played[p] for e, p in pairs}
    paired_played = {p for _, p in pairs}
    window_bars = played_window(expected, pairs)
    notes = [
        _note_result(note, grid["offset_s"] + note.onset_beats * grid["sec_per_beat"], partner.get(index), tuning)
        for index, note in enumerate(expected)
    ]
    if window_bars is not None:
        notes = [
            _not_played(result) if not window_bars[0] <= result["bar"] <= window_bars[1] else result
            for result in notes
        ]
    judged = [note for note in notes if note["status"] != config.STATUS_NOT_PLAYED]
    window = _outside_window(expected, played, pairs, beat_s)
    extras = []
    outside_count = 0
    for index, note in enumerate(played):
        if index in paired_played:
            continue
        if window and not window[0] <= note["onset_s"] <= window[1]:
            outside_count += 1
        elif note["confidence"] >= config.CONFIDENCE_THRESHOLD:
            beat = (note["onset_s"] - grid["offset_s"]) / grid["sec_per_beat"]
            extras.append(_extra(take_id, note, _bar_at(bar_starts, beat)))
    ok_count = sum(1 for note in judged if note["status"] == config.STATUS_OK)
    quality = ok_count / len(judged) if judged else 0.0
    score_quality = ok_count / len(notes) if notes else 0.0
    reason = cant_tell_reason(len(judged), len(pairs), quality)
    return {
        "notes": notes,
        "extras": extras,
        "outside_count": outside_count,
        "tuning_cents": round(tuning * config.CENTS_PER_SEMITONE),
        "played_bars": list(window_bars) if window_bars else None,
        "not_played_count": len(notes) - len(judged),
        "alignment_quality": quality,
        "score_quality": score_quality,
        "cant_tell": reason is not None,
        "cant_tell_reason": reason,
    }
