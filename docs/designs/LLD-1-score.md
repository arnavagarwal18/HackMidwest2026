# LLD-1 Score ingest - change 3: Score model and file parsing

Approved design LLD-1 (id 01a12743-2843-72d4-9fee-83bc20614456), proposed change 3
(item 01a12746-702f-7491-830a-b66932067f19). Text as given to the coder.

## Score model

Saved as `data/sessions/{id}/score.json`:

```
{ title: str, instrument: str,
  tempo_bpm: float            (first tempo mark, else 90),
  time_signature: [int, int]  (first one, else 4/4),
  written_transpose_semitones: int|null  (MusicXML transpose chromatic value, else null),
  bars: [ { bar: int (1-based),
            start_beat: float (quarter-note beats from start),
            beats: float (bar length in quarter notes),
            notes: [ { idx: int (0-based in bar),
                       pitch_midi: int|null (null = rest),
                       name: str ('E5' or 'rest'),
                       start_beat: float (absolute),
                       dur_beats: float,
                       tied_from_previous: bool } ] } ],
  warnings: [str] }
```

Written pitch is stored (no transposition). Only the first part is kept; for a chord only
the top note, with a warning (e.g. 'Chords found: only the top note is checked.').

## Parse (backend/app/score/parse.py, music21)

MusicXML, .mxl, MIDI; keep first part (warning if several parts); top note of chords +
warning; first tempo mark (default 90), first time signature (default 4/4), any transpose
chromatic value. MIDI: first track with notes, round starts and lengths to the nearest
16th. File that can't be parsed or has no notes -> raise BadScoreFile.

## Python interface (backend/app/score/api.py)

`get_score(session_id) -> Score` dataclass (raises NotConfirmed unless score_status is
'confirmed'; reads status via app.store once it exists, meanwhile an injectable
loader/stub); `bar_at_beat(score, beat) -> int`; `beats_to_seconds(beats, tempo_bpm) ->
float`. Score dataclass with to_json/from_json.

## Tests

- trumpet MusicXML with transpose -2 gives written_transpose_semitones -2
- a two-part file keeps part 1 with a warning
- chords keep top notes with a warning
- a MIDI file gives notes rounded to 16ths
- broken XML raises BadScoreFile
- bar_at_beat / beats_to_seconds cases

Small fixtures live in backend/tests/fixtures/. Built-in pieces are change 4.
