"""Builders for score.json-shaped dicts and played notes used by the diagnosis tests."""
from app.diagnosis.expected import midi_to_name

QUARTER_BAR_BEATS = 4.0
SCALE_BARS = [
    [60, 62, 64, 65],
    [67, 69, 71, 72],
    [72, 71, 69, 67],
    [65, 64, 62, 60],
]


def make_score(bars: list[list], beats_per_note: float = 1.0) -> dict:
    """bars: per bar a list of notes; a note is a midi int, None (rest) or (midi, 'tied')."""
    score_bars = []
    for bar_number, notes in enumerate(bars, start=1):
        bar_start = (bar_number - 1) * QUARTER_BAR_BEATS
        score_notes = []
        for idx, note in enumerate(notes):
            tied = isinstance(note, tuple)
            midi = note[0] if tied else note
            score_notes.append(
                {
                    "idx": idx,
                    "pitch_midi": midi,
                    "name": "rest" if midi is None else midi_to_name(midi),
                    "start_beat": bar_start + idx * beats_per_note,
                    "dur_beats": beats_per_note,
                    "tied_from_previous": tied,
                }
            )
        score_bars.append(
            {"bar": bar_number, "start_beat": bar_start, "beats": QUARTER_BAR_BEATS, "notes": score_notes}
        )
    return {
        "title": "Test scale",
        "instrument": "violin",
        "tempo_bpm": 120,
        "time_signature": [4, 4],
        "written_transpose_semitones": None,
        "bars": score_bars,
        "warnings": [],
    }


def make_scale_score() -> dict:
    return make_score(SCALE_BARS)


def played_note(i: int, onset_s: float, midi: float, confidence: float = 1.0) -> dict:
    rounded = round(midi)
    return {
        "i": i,
        "onset_s": onset_s,
        "offset_s": onset_s + 0.4,
        "midi_float": float(midi),
        "midi": rounded,
        "cents_off": (midi - rounded) * 100,
        "confidence": confidence,
        "voiced_ratio": 1.0,
    }


def make_take(**overrides) -> dict:
    take = {
        "take_id": "t1",
        "bar_from": 1,
        "bar_to": 4,
        "tempo_bpm": 120,
        "downbeat_s": 1.0,
        "latency_s": 0.0,
    }
    return {**take, **overrides}


def perfect_played(midis: list[int], offset_s: float = 1.0, sec_per_beat: float = 0.5) -> list[dict]:
    """One quarter-note-spaced played note per midi, exactly on the grid."""
    return [played_note(i, offset_s + i * sec_per_beat, midi) for i, midi in enumerate(midis)]
