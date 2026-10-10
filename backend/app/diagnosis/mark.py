"""Step 4: mark each expected note ok / wrong / uncertain / missed, collect Extras, judge the match."""
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


def _pair_status(played: dict, expected_midi: int) -> str:
    if abs(played["midi_float"] - expected_midi) <= config.OK_TOLERANCE_SEMITONES:
        return config.STATUS_OK
    if played["confidence"] < config.CONFIDENCE_THRESHOLD:
        return config.STATUS_UNCERTAIN
    return config.STATUS_WRONG


def _note_result(note: ExpectedNote, expected_onset_s: float, played: dict | None) -> dict:
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
        result.update(
            status=_pair_status(played, note.midi),
            played_i=played["i"],
            played_name=midi_to_name(played["midi"]),
            played_midi_float=played["midi_float"],
            cents_off=round((played["midi_float"] - note.midi) * config.CENTS_PER_SEMITONE, 2),
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


def mark_alignment(
    take_id: str,
    expected: list[ExpectedNote],
    played: list[dict],
    pairs: list[Pair],
    grid: dict,
    bar_starts: list[tuple[int, float]],
    beat_s: float,
) -> dict:
    """Returns notes, extras, outside_count, alignment_quality, cant_tell and cant_tell_reason.

    `beat_s` is seconds per beat (the step 3 fit's, else from the target tempo). An unpaired played note
    far before the first pair or after the last pair's end is outside the range: counted, never an Extra.
    """
    partner = {e: played[p] for e, p in pairs}
    paired_played = {p for _, p in pairs}
    notes = [
        _note_result(note, grid["offset_s"] + note.onset_beats * grid["sec_per_beat"], partner.get(index))
        for index, note in enumerate(expected)
    ]
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
    ok_count = sum(1 for note in notes if note["status"] == config.STATUS_OK)
    quality = ok_count / len(expected) if expected else 0.0
    reason = cant_tell_reason(len(expected), len(pairs), quality)
    return {
        "notes": notes,
        "extras": extras,
        "outside_count": outside_count,
        "alignment_quality": quality,
        "cant_tell": reason is not None,
        "cant_tell_reason": reason,
    }
