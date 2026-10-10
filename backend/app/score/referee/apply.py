"""Applies the referee's accepted rulings to the score and the doubtful-bar list. Pure code, no model.

- Accepted 'reader': that bar's notes in the Score are replaced by the reader's (pitch from the
  name, length from the length word, through note_text's spelling). The bar must exist in the
  Score: a bar only the reader found has nowhere to go, so it is 'apply_failed'.
- Accepted 'homr': nothing changes in the Score.
- Accepted bars leave doubtful_bars. Every other bar stays, with referee_note set to the
  referee's reason if it ruled on it, else None.
- A reader bar that cannot be converted turns its ruling into accepted False, 'apply_failed',
  and the bar stays doubtful.
The inputs are not changed; copies are returned.
"""
import copy
import logging
from typing import Callable

from app.score.compare import CompareResult
from app.score.model import Bar, Note, Score
from app.score.reading import ReadBar
from app.score.referee.checks import length_beats, parse_pitch, pitch_midi, reader_keys
from app.score.referee.result import Ruling

logger = logging.getLogger(__name__)

NO_BAR_TO_REPLACE = "the score has no such bar"


class ApplyError(Exception):
    """A reader bar could not be turned into score notes; the message says which note and why."""


def convert_reader_bar(bar: Bar, read_bar: ReadBar) -> Bar:
    """A copy of `bar` with the reader's notes in place of its own."""
    notes: list[Note] = []
    cursor = bar.start_beat
    for idx, (name, length) in enumerate(reader_keys(read_bar)):
        beats = length_beats(length)
        if beats is None:
            raise ApplyError(f"bar {bar.bar}: cannot read the length '{length}'")
        if name == "rest":
            midi = None
        elif parse_pitch(name) is None:
            raise ApplyError(f"bar {bar.bar}: cannot read the pitch '{name}'")
        else:
            midi = pitch_midi(name)
        notes.append(Note(idx=idx, pitch_midi=midi, name=name, start_beat=round(cursor, 4), dur_beats=beats))
        cursor += beats
    return Bar(bar=bar.bar, start_beat=bar.start_beat, beats=bar.beats, notes=notes)


def _replace_bar(score: Score, read_bar: ReadBar | None) -> None:
    if read_bar is None:
        raise ApplyError("the reader has no such bar")
    for position, bar in enumerate(score.bars):
        if bar.bar == read_bar.bar:
            score.bars[position] = convert_reader_bar(bar, read_bar)
            return
    raise ApplyError(f"bar {read_bar.bar}: {NO_BAR_TO_REPLACE}")


def apply_rulings(
    score: Score, compare: CompareResult, rulings: list[Ruling], reader_bar: Callable[[int], ReadBar | None],
) -> tuple[Score, CompareResult, list[Ruling]]:
    """The score with accepted reader bars in, the shrunk and annotated compare, and the final rulings."""
    new_score = copy.deepcopy(score)
    final: list[Ruling] = []
    for ruling in rulings:
        ruling = Ruling(**ruling)
        if ruling["accepted"] and ruling["pick"] == "reader":
            try:
                _replace_bar(new_score, reader_bar(ruling["bar"]))
            except ApplyError as exc:
                logger.error("Referee: could not apply the reader's bar %s: %s", ruling["bar"], exc)
                ruling["accepted"], ruling["rejected_because"] = False, "apply_failed"
        final.append(ruling)
    accepted = {r["bar"] for r in final if r["accepted"]}
    notes = {r["bar"]: r["why"] for r in final if not r["accepted"]}
    remaining = [
        {**entry, "referee_note": notes.get(entry["bar"])}
        for entry in compare.doubtful_bars
        if entry["bar"] not in accepted
    ]
    new_compare = CompareResult(doubtful_bars=remaining, double_checked=compare.double_checked,
                                warnings=list(compare.warnings))
    return new_score, new_compare, final
