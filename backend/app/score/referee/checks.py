"""Code checks on one reading of one bar: does it add up, is it playable, does it fit the key?

Plain code, no model. Both readings are first put in note_text's (name, length) form, so a pitch
is a normalised name ('F#4', 'Bb3', 'rest') and a length is a word ('quarter', 'dotted half').
- length_ok: the note lengths add up to the bar length of the time signature. The first bar may
  be a pickup (shorter, never longer). A bar whose lengths can't all be understood, or with no
  notes, is not length_ok.
- range_ok: every pitch is inside the trumpet's written range. A pitch we can't parse is not.
- key_ok: no note contradicts the key signature, unless an earlier note of the same letter and
  octave in the bar already carries that accidental. A natural sign is dropped when names are
  normalised, so a natural against the key shows as a contradiction here. With an unknown key
  (key_fifths None) there is nothing to contradict, so key_ok is true.
"""
import re

from app.score.model import Bar
from app.score.note_text import BASE_BEATS, REST, normalise_name, read_note_key
from app.score.reading import ReadBar
from app.score.referee import config
from app.score.referee.result import BarCheck

NoteKeys = list[tuple[str, str]]

SHARP_ORDER = "FCGDAEB"
FLAT_ORDER = "BEADGCF"
SEMITONE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_PITCH = re.compile(r"^([A-G])([#b]*)(-?\d+)$")


def length_beats(length: str) -> float | None:
    """'quarter' -> 1.0, 'dotted half' -> 3.0; None when the length word is not one we know."""
    dotted = length.startswith("dotted ")
    base = BASE_BEATS.get(length.removeprefix("dotted "))
    if base is None:
        return None
    return base * 1.5 if dotted else base


def parse_pitch(name: str) -> tuple[str, int, int] | None:
    """'F#4' -> ('F', 1, 4): letter, accidental in semitones, octave; None if not a pitch with an octave."""
    match = _PITCH.match(normalise_name(name))
    if not match:
        return None
    letter, marks, octave = match.groups()
    return letter, marks.count("#") - marks.count("b"), int(octave)


def pitch_midi(name: str) -> int | None:
    parsed = parse_pitch(name)
    if parsed is None:
        return None
    letter, accidental, octave = parsed
    return 12 * (octave + 1) + SEMITONE[letter] + accidental


def key_accidental(letter: str, key_fifths: int) -> int:
    """The accidental the key signature puts on `letter`: +1, -1 or 0."""
    if key_fifths > 0:
        return 1 if letter in SHARP_ORDER[:key_fifths] else 0
    return -1 if letter in FLAT_ORDER[:-key_fifths] else 0


def _range_ok(pitches: list[str]) -> bool:
    for name in pitches:
        midi = pitch_midi(name)
        if midi is None or not config.LOWEST_MIDI <= midi <= config.HIGHEST_MIDI:
            return False
    return True


def _key_ok(pitches: list[str], key_fifths: int | None) -> bool:
    if key_fifths is None:
        return True
    carried: dict[tuple[str, int], int] = {}
    for name in pitches:
        parsed = parse_pitch(name)
        if parsed is None:
            continue  # range_ok already reports a pitch we can't read
        letter, accidental, octave = parsed
        expected = carried.get((letter, octave), key_accidental(letter, key_fifths))
        if accidental != expected:
            return False
        carried[(letter, octave)] = accidental
    return True


def _length_ok(beats: float | None, expected: float, is_first_bar: bool) -> bool:
    if beats is None or beats <= 0:
        return False
    if abs(beats - expected) <= config.LENGTH_TOLERANCE_BEATS:
        return True
    return is_first_bar and beats < expected


def check_bar(pitches: list[str], beats: float | None, time_signature: tuple[int, int], key_fifths: int | None,
              is_first_bar: bool) -> BarCheck:
    """Run the three checks on one reading of a bar: its normalised pitch names (rests as 'rest') and total beats.

    `beats` is None when some note's length could not be understood.
    """
    expected = time_signature[0] * 4 / time_signature[1]
    sounding = [name for name in pitches if name != REST]
    return BarCheck(
        length_ok=_length_ok(beats, expected, is_first_bar),
        range_ok=_range_ok(sounding),
        key_ok=_key_ok(sounding, key_fifths),
        beats=beats or 0.0,
        expected_beats=expected,
    )


def check_homr_bar(bar: Bar, time_signature: tuple[int, int], key_fifths: int | None, is_first_bar: bool) -> BarCheck:
    pitches = [normalise_name(note.name) for note in bar.notes]
    beats = sum(note.dur_beats for note in bar.notes)
    return check_bar(pitches, beats, time_signature, key_fifths, is_first_bar)


def check_reader_bar(read_bar: ReadBar, time_signature: tuple[int, int], key_fifths: int | None,
                     is_first_bar: bool) -> BarCheck:
    keys = reader_keys(read_bar)
    lengths = [length_beats(length) for _, length in keys]
    beats = None if any(length is None for length in lengths) else sum(lengths)
    return check_bar([name for name, _ in keys], beats, time_signature, key_fifths, is_first_bar)


def reader_keys(read_bar: ReadBar) -> NoteKeys:
    return [read_note_key(note.name, note.length) for note in read_bar.notes]
