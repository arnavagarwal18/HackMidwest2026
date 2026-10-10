# Hot Cross Buns clean take: result

Source (not committed): `C:\Users\Xavier Sorto\Downloads\Hacksmidwest Training Data\Hot Cross Buns - Trumpet - DigiTide Blaze (1080p).mp4` (13.4 s). AI off (`AI_ENABLED=false`).

Command (server: `AI_ENABLED=false uvicorn app.main:app --app-dir backend --port 8000`):
`python backend/scripts/e2e_real.py testdata/hot_cross_buns/score.musicxml <source mp4> --bars 1-4 --bpm 83`

Played (app transcription, concert pitch): D4 C4 Bb3 | D4 C4 Bb3 | Bb3 x4, C4 x4 (eighths) | D4 C4 Bb3 (held).
This is the standard tune, no repeats. `score.musicxml` is Trumpet in Bb (written E D C = concert D C Bb), 4/4, 4 bars, quarter = 83.

| Measure | Value |
|---|---|
| Alignment quality | 0.94 (target >= 0.8: met) |
| Notes | 17 expected: 16 ok, 1 wrong, 0 missed |
| Extras / outside | 0 / 0 (no note has an "outside" status) |
| Tempo | played 83.57 BPM vs score 83 (bars 1-2 about 81, bar 3 about 91, bar 4 about 83) |
| Form analysis | `form_status: failed` (not part of this test; not investigated) |

False mistake (target "no wrong notes": missed by one note): bar 3, note 5 (second half of the bar, first C4 after the four Bb3). It was heard as C#4 (60.52, +52 cents), so it counts as wrong. The other C4s read +22 to +32 cents; the player is about 25 cents sharp throughout (no calibration run).
Also reported as problems (true to the performance, not errors in the data): "Bar 3: 2 notes late, 113 ms on average" and "Bar 3: rushing, about 10% faster than 83 BPM". The player speeds up in bar 3 (eighths 0.33 s apart, about 91 BPM) and holds about 83 BPM elsewhere, so one metronome mark cannot fit every bar.

Guess (not verified): the wrong note is a pitch-tracking error on a short (0.13 s) note. Its median pitch lands at 60.52, just over the half-semitone rounding line, because the player is already about 25 cents sharp and this note is the sharpest of the C4s. A pitch offset from calibration, or rounding against the note's own offset, would likely make it ok.
