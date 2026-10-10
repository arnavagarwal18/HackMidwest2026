"""Bar comparison: where homr's reading of the scan and the reader agent's reading disagree.

Plain code, no model. Both sides are put in the same (name, length) form by app.score.note_text
(see its docstring for the spelling, rest, length and tie choices). A bar is doubtful when the
reader has no such bar, the note lists differ in length, or any pair differs in name or length.
Bars only the reader has are listed with homr_text '(no notes read)'.

Choices made here:
- A reading with no bars at all counts as 'no reading' (it checks nothing).
- If the reader repeats a bar number, its first entry for that bar is used.
- "More than half the bars" is counted over every bar number either side has (homr's bars plus
  any extra reader bars). Exactly half doubtful is still reported bar by bar.
- doubtful_bars come in bar order.
"""
from dataclasses import dataclass, field
from typing import TypedDict

from app.score.model import Score
from app.score.note_text import homr_bar_keys, read_note_key, write_out
from app.score.reading import Reading

NO_READING_WARNING = "We couldn't double-check this scan: compare it with your copy before you confirm."
MOSTLY_DIFFERENT_WARNING = "The two readings disagree on most bars: check the whole page against your copy."
NO_NOTES_TEXT = "(no notes read)"

NoteKeys = list[tuple[str, str]]


class DoubtfulBar(TypedDict):
    bar: int
    homr_text: str
    reader_text: str | None


@dataclass
class CompareResult:
    doubtful_bars: list[DoubtfulBar] = field(default_factory=list)
    double_checked: bool = False
    warnings: list[str] = field(default_factory=list)


def _reader_bars(reading: Reading) -> dict[int, NoteKeys]:
    bars: dict[int, NoteKeys] = {}
    for read_bar in reading.bars:
        bars.setdefault(read_bar.bar, [read_note_key(n.name, n.length) for n in read_bar.notes])
    return bars


def _doubtful(bar: int, homr: NoteKeys | None, reader: NoteKeys | None) -> DoubtfulBar | None:
    if homr is not None and reader is not None and homr == reader:
        return None
    return DoubtfulBar(
        bar=bar,
        homr_text=write_out(homr) if homr else NO_NOTES_TEXT,
        reader_text=None if reader is None else write_out(reader),
    )


def compare_bars(score: Score, reading: Reading | None) -> CompareResult:
    """Compare homr's score with the reader's reading; no reading means 'not double-checked'."""
    if reading is None or not reading.bars:
        return CompareResult(warnings=[NO_READING_WARNING])
    reader = _reader_bars(reading)
    homr = {bar.bar: homr_bar_keys(bar) for bar in score.bars}
    bar_numbers = sorted(homr.keys() | reader.keys())
    doubtful = [
        entry
        for number in bar_numbers
        if (entry := _doubtful(number, homr.get(number), reader.get(number))) is not None
    ]
    if len(doubtful) * 2 > len(bar_numbers):
        return CompareResult(warnings=[MOSTLY_DIFFERENT_WARNING])
    return CompareResult(doubtful_bars=doubtful, double_checked=True)
