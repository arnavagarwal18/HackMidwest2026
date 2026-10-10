"""Puts notes from homr's score model and from the reader agent into one comparable form.

Choices made here (the same for both sides, so only a real difference shows up):
- Pitch names: the letter is upper case; sharps and flats are written '#' and 'b', so 'Bb4',
  'B-4', 'B♭4', 'b flat 4' and 'B-flat4' are all 'Bb4'; naturals ('♮', 'natural') are dropped.
  Spelling is kept as written: 'C#4' and 'Db4' are different notes (homr and the reader both
  report the printed note, so a different spelling is a real disagreement). A missing octave
  stays missing, so 'E' does not equal 'E5'.
- Rests: 'rest', 'Rest', 'r' and 'pause' are all 'rest'.
- Lengths: 'sixteenth', '16th', 'semiquaver' are all '16th'; likewise eighth/8th/quaver,
  quarter/crotchet, half/minim, whole/semibreve. 'dotted' may come before or after the length
  or as a trailing '.', and is always written first: 'dotted quarter'.
- homr's lengths come from dur_beats (quarter-note beats). A duration that is not a plain or
  dotted note (e.g. a triplet) is written as '<n> beats', which never equals a reader length.
- Tied notes are not merged: a note tied from the previous one is its own note on both sides,
  as it is on the printed page.
"""
import re

from app.score.model import Bar, Note

REST = "rest"
DURATION_TOLERANCE = 1e-3
# quarter-note beats of each undotted length
BASE_BEATS = {"whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5, "16th": 0.25, "32nd": 0.125}
_LENGTH_WORDS = {
    "whole": "whole", "semibreve": "whole", "1": "whole", "1/1": "whole",
    "half": "half", "minim": "half", "2": "half", "1/2": "half", "2nd": "half",
    "quarter": "quarter", "crotchet": "quarter", "4": "quarter", "1/4": "quarter", "4th": "quarter",
    "eighth": "eighth", "quaver": "eighth", "8": "eighth", "1/8": "eighth", "8th": "eighth",
    "sixteenth": "16th", "semiquaver": "16th", "16": "16th", "1/16": "16th", "16th": "16th",
    "thirty second": "32nd", "thirtysecond": "32nd", "demisemiquaver": "32nd", "32": "32nd",
    "1/32": "32nd", "32nd": "32nd",
}
_REST_WORDS = {"rest", "r", "pause"}
_PITCH = re.compile(r"^([a-g])\s*((?:#|♯|b|♭|-|sharp|flat|natural|♮)*)\s*(-?\d+)?$")
_ACCIDENTALS = {"#": "#", "♯": "#", "sharp": "#", "b": "b", "♭": "b", "flat": "b", "-": "b", "♮": "", "natural": ""}


def normalise_name(name: str) -> str:
    """'B♭4' -> 'Bb4'; 'rest' for rests; anything unrecognised is returned trimmed (so it will not match)."""
    text = " ".join(name.split())
    lowered = text.lower()
    if lowered in _REST_WORDS:
        return REST
    match = _PITCH.match(lowered.replace("-flat", "flat").replace("-sharp", "sharp"))
    if not match:
        return text
    letter, accidentals, octave = match.groups()
    marks = "".join(_ACCIDENTALS[token] for token in re.findall(r"#|♯|b|♭|-|sharp|flat|natural|♮", accidentals))
    return letter.upper() + marks + (octave or "")


def normalise_length(length: str) -> str:
    """'Dotted Quarter', 'quarter dotted' or 'quarter.' -> 'dotted quarter'."""
    text = " ".join(length.lower().replace("_", " ").replace("-", " ").split())
    dotted = "dotted" in text.split() or text.endswith(".")
    base_text = " ".join(word for word in text.replace(".", "").split() if word not in ("dotted", "note"))
    base = _LENGTH_WORDS.get(base_text)
    if base is None:
        return text
    return f"dotted {base}" if dotted else base


def length_from_beats(dur_beats: float) -> str:
    for base, beats in BASE_BEATS.items():
        if abs(dur_beats - beats) <= DURATION_TOLERANCE:
            return base
        if abs(dur_beats - beats * 1.5) <= DURATION_TOLERANCE:
            return f"dotted {base}"
    return f"{dur_beats:g} beats"


def homr_note_key(note: Note) -> tuple[str, str]:
    return normalise_name(note.name), length_from_beats(note.dur_beats)


def read_note_key(name: str, length: str) -> tuple[str, str]:
    return normalise_name(name), normalise_length(length)


def write_out(keys: list[tuple[str, str]]) -> str:
    """[('E5', 'quarter'), ('D5', 'half')] -> 'E5 quarter, D5 half'."""
    return ", ".join(f"{name} {length}" for name, length in keys)


def homr_bar_keys(bar: Bar) -> list[tuple[str, str]]:
    return [homr_note_key(note) for note in bar.notes]
