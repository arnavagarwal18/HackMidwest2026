"""Parse MusicXML, .mxl and MIDI files into a Score using music21."""
from __future__ import annotations

import logging
from pathlib import Path

from music21 import converter, instrument, key, meter, stream, tempo

from app.score.bars import RawEvent, build_bars, round_to_16th, synthesize_spans
from app.score.exceptions import BadScoreFile, NoNotes
from app.score.model import Score

logger = logging.getLogger(__name__)

MUSICXML_SUFFIXES = {".xml", ".musicxml", ".mxl"}
MIDI_SUFFIXES = {".mid", ".midi"}
DEFAULT_TEMPO_BPM = 90.0
DEFAULT_TIME_SIGNATURE = (4, 4)

WARNING_SEVERAL_PARTS = "Several parts found: only the first part is kept."
WARNING_CHORDS = "Chords found: only the top note is checked."


def parse_score_file(path: str | Path) -> Score:
    """Read a score file; raises BadScoreFile if it can't be parsed or has no notes."""
    path = Path(path)
    suffix = path.suffix.lower()
    is_midi = suffix in MIDI_SUFFIXES
    if not is_midi and suffix not in MUSICXML_SUFFIXES:
        raise BadScoreFile(f"Unsupported file type '{path.suffix}'. Use MusicXML (.xml, .musicxml, .mxl) or MIDI (.mid, .midi).")

    parsed = _load(path)
    parts_with_notes = [part for part in _parts(parsed) if len(part.flatten().notes) > 0]
    if not parts_with_notes:
        logger.error("Score file %s contains no notes", path)
        raise NoNotes(f"{path.name} contains no notes.")

    warnings: list[str] = []
    if len(parts_with_notes) > 1:
        warnings.append(WARNING_SEVERAL_PARTS)
    part = parts_with_notes[0]

    events, has_chords = _read_events(part, quantize=is_midi)
    if has_chords:
        warnings.append(WARNING_CHORDS)

    time_signature = _first_time_signature(parsed)
    spans = _bar_spans(part, time_signature, max(e.start + e.dur for e in events))
    return Score(
        title=_title(parsed, path),
        instrument=_instrument_name(part),
        tempo_bpm=_first_tempo(parsed),
        time_signature=time_signature,
        written_transpose_semitones=_written_transpose(part),
        bars=build_bars(events, spans, fill_rests=is_midi),
        warnings=warnings,
        key_fifths=_first_key_fifths(parsed),
    )


def _load(path: Path) -> stream.Stream:
    try:
        return converter.parse(str(path))
    except Exception as exc:  # music21 and the XML/zip layers raise many unrelated types
        logger.exception("Could not parse score file %s", path)
        raise BadScoreFile(f"{path.name} could not be read as a score: {exc}") from exc


def _parts(parsed: stream.Stream) -> list[stream.Stream]:
    if isinstance(parsed, stream.Score):
        return list(parsed.parts)
    return [parsed]


def _read_events(part: stream.Stream, quantize: bool) -> tuple[list[RawEvent], bool]:
    events: list[RawEvent] = []
    has_chords = False
    for element in part.flatten().notesAndRests:
        if element.duration.isGrace:
            continue
        start, dur = float(element.offset), float(element.quarterLength)
        if quantize:
            start, dur = round_to_16th(start), max(round_to_16th(dur), 0.25)
        if element.isRest:
            events.append(RawEvent(start, dur, None, "rest"))
            continue
        note = element
        if element.isChord:
            has_chords = True
            note = max(element.notes, key=lambda n: n.pitch.midi)
        tied = note.tie is not None and note.tie.type in ("stop", "continue")
        events.append(RawEvent(start, dur, note.pitch.midi, note.pitch.nameWithOctave.replace("-", "b"), tied))
    return events, has_chords


def _bar_spans(part: stream.Stream, time_signature: tuple[int, int], end_beat: float) -> list[tuple[float, float]]:
    """(start, length) per bar: from measures when the file has them, else from the time signature."""
    measures = list(part.getElementsByClass(stream.Measure))
    if not measures:
        numerator, denominator = time_signature
        return synthesize_spans(numerator * 4 / denominator, end_beat)
    starts = [float(m.offset) for m in measures]
    lengths = [nxt - cur for cur, nxt in zip(starts, starts[1:])]
    last = measures[-1]
    lengths.append(max(float(last.barDuration.quarterLength), float(last.highestTime)))
    return list(zip(starts, lengths))


def _first_time_signature(parsed: stream.Stream) -> tuple[int, int]:
    for signature in parsed.flatten().getElementsByClass(meter.TimeSignature):
        return signature.numerator, signature.denominator
    return DEFAULT_TIME_SIGNATURE


def _first_key_fifths(parsed: stream.Stream) -> int | None:
    for signature in parsed.flatten().getElementsByClass(key.KeySignature):
        return int(signature.sharps)
    return None


def _first_tempo(parsed: stream.Stream) -> float:
    for mark in parsed.flatten().getElementsByClass(tempo.MetronomeMark):
        bpm = mark.getQuarterBPM()
        if bpm:
            return float(bpm)
    return DEFAULT_TEMPO_BPM


def _written_transpose(part: stream.Stream) -> int | None:
    for inst in part.flatten().getElementsByClass(instrument.Instrument):
        if inst.transposition is not None:
            return int(inst.transposition.chromatic.semitones)
    return None


def _instrument_name(part: stream.Stream) -> str:
    for inst in part.flatten().getElementsByClass(instrument.Instrument):
        if inst.instrumentName:
            return inst.instrumentName
    return getattr(part, "partName", None) or "Unknown"


def _title(parsed: stream.Stream, path: Path) -> str:
    metadata = getattr(parsed, "metadata", None)
    return (metadata.title if metadata is not None and metadata.title else None) or path.stem
