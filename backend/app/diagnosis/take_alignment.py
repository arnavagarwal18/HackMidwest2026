"""Entry point for steps 1, 3 and 4 of note diagnosis."""
from .align import align_notes, build_grid
from .errors import input_error
from .expected import bar_start_beats, build_expected_notes
from .mark import mark_alignment

PLAYED_KEYS = ("i", "onset_s", "midi_float", "midi", "confidence")
TAKE_KEYS = ("take_id", "bar_from", "bar_to", "tempo_bpm")


def _check_inputs(played: list[dict], take: dict) -> None:
    missing_take = [key for key in TAKE_KEYS if key not in take]
    if missing_take:
        raise input_error(f"The take is missing {missing_take}.")
    if not take["tempo_bpm"] or take["tempo_bpm"] <= 0:
        raise input_error(f"The take's tempo_bpm must be above 0, got {take['tempo_bpm']}.")
    for note in played:
        missing = [key for key in PLAYED_KEYS if key not in note]
        if missing:
            raise input_error(f"Played note {note.get('i', '?')} is missing {missing}.")


def align_take(score: dict, played: list[dict], take: dict, transposition_semitones: int) -> dict:
    """Line a take's played notes up with the score's notes and mark each expected note.

    Returns {notes, extras, grid, fit, alignment_quality, cant_tell, cant_tell_reason}; `fit` is
    {offset_s, sec_per_beat} or None. Raises DiagnosisInputError for unusable input.
    """
    _check_inputs(played, take)
    expected = build_expected_notes(
        score, take["take_id"], take["bar_from"], take["bar_to"], transposition_semitones
    )
    played_in_order = sorted(played, key=lambda note: note["onset_s"])
    alignment = align_notes(expected, played_in_order)
    grid = build_grid(
        expected,
        played_in_order,
        alignment,
        take.get("downbeat_s"),
        take.get("latency_s") or 0.0,
        take["tempo_bpm"],
    )
    marked = mark_alignment(
        take["take_id"],
        expected,
        played_in_order,
        alignment.pairs,
        grid,
        bar_start_beats(score, take["bar_from"], take["bar_to"]),
    )
    fit = None
    if alignment.fit is not None:
        fit = {"offset_s": alignment.fit.offset_s, "sec_per_beat": alignment.fit.sec_per_beat}
    return {**marked, "grid": grid, "fit": fit}
