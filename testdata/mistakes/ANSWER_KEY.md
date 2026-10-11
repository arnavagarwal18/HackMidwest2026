# Mistake takes: answer key

Six trumpet takes with known mistakes, made by `testdata/tools/make_mistake_takes.py` from three real recordings (`backend/.venv/bin/python testdata/tools/make_mistake_takes.py`). Each source has a `wrong_note` take and a `missed_and_rushing` take, in `testdata/mistakes/<source>/`. All are 1280x720, 3-5 MB.

How to read this key
- Bars and beats are the score's (beat 1 is the first beat of the bar; 3.5 is the "and" of beat 3). Note names are the sounding (concert) pitch the app expects; a Bb trumpet's written note is 2 semitones higher.
- Timestamps are seconds in the video. The note times were taken from the app's own transcription of the unmodified recordings (see the Baseline rows in Results).
- `wrong_note`: the audio over just that note's span (onset minus 20 ms to offset plus 20 ms, 10 ms cross-fades) is pitch-shifted by one semitone (librosa `pitch_shift`). The video and every other note are untouched, so the timing of everything else is identical to the source.
- `missed_and_rushing`, missed note: the audio over the note's span is silenced (the player skipped it and kept time; the video still shows the player). Bar 11 of Ode to Joy needed 170 ms of silence after the note's end, because the release rang on for about 100 ms past the transcribed end (a shorter silence left a 110 ms B4 that the app heard as a note).
- `missed_and_rushing`, rushing: the audio of one 4-bar phrase (bars 5-8 in all three) is time-stretched 1.15x (15% faster, pitch kept); the video of the same stretch is sped up by the same factor. Because the take is shorter after the phrase, everything after it is earlier in the take than in the source by the phrase's saved time (the "shift" below); the missed note sits after the phrase, so its take time is its source time minus the shift.
- Every edited note differs in pitch from both neighbours after the edit (no repeated same-pitch pairs made). The sources themselves have same-pitch neighbours (Ode to Joy B B, G G; video1 D5 D5; video2 C#5 C#5 C#5): not edited, but they can affect scoring.

## Ode to Joy: `testdata/ode_to_joy/ode_to_joy_trumpet11.mp4`, score `testdata/ode_to_joy/score.musicxml` (16 bars, quarter = 100)

`ode_to_joy/ode_to_joy_wrong_note.mp4`

| # | Bar, beat | Source time | Original | In the take |
|---|---|---|---|---|
| 1 | 3, beat 3 | 8.21-8.71 s | A4 | G#4 (down 1 semitone) |
| 2 | 14, beat 2 | 34.03-34.49 s | C5 | C#5 (up 1 semitone) |

`ode_to_joy/ode_to_joy_missed_and_rushing.mp4`

| # | What | Bars | Source time | Take time |
|---|---|---|---|---|
| 1 | Rushing 15% (phrase 11.5-21.1 s, 9.6 s long) | 5-8 | 11.5-21.1 s | 11.5-19.85 s (shift after it: 1.25 s earlier) |
| 2 | Missed note B4 (silenced) | 11, beat 3 | 27.38-27.79 s | 26.13-26.54 s |

## trumpet_video1: `testdata/trumpet_video1.mp4`, score `testdata/trumpet_video1_sheet.webp` (scanned: 16 bars, quarter = 90; played about 64 BPM)

`trumpet_video1/trumpet_video1_wrong_note.mp4`

| # | Bar, beat | Source time | Original | In the take |
|---|---|---|---|---|
| 1 | 3, beat 3.5 | 11.31-11.67 s | A4 | G#4 (down 1) |
| 2 | 13, beat 3.5 | 48.79-49.89 s | G5 | G#5 (up 1) |

`trumpet_video1/trumpet_video1_missed_and_rushing.mp4`

| # | What | Bars | Source time | Take time |
|---|---|---|---|---|
| 1 | Rushing 15% (phrase 16.33-31.10 s, 14.77 s long) | 5-8 | 16.33-31.10 s | 16.33-29.17 s (shift after it: 1.93 s earlier) |
| 2 | Missed note D5 (silenced) | 14, beat 2.5 | 51.78-52.20 s | 49.85-50.27 s |

## trumpet_video2: `testdata/trumpet_video2.mp4`, score `testdata/trumpet_video2_sheet.webp` (scanned: 20 bars, quarter = 90; played about 94 BPM)

`trumpet_video2/trumpet_video2_wrong_note.mp4`

| # | Bar, beat | Source time | Original | In the take |
|---|---|---|---|---|
| 1 | 6, beat 3 | 16.78-17.37 s | A#4 | B4 (up 1) |
| 2 | 9, beat 3 | 24.53-24.81 s | B3 | A#3 (down 1) |

`trumpet_video2/trumpet_video2_missed_and_rushing.mp4`

| # | What | Bars | Source time | Take time |
|---|---|---|---|---|
| 1 | Rushing 15% (phrase 12.7-22.9 s, 10.2 s long) | 5-8 | 12.7-22.9 s | 12.7-21.57 s (shift after it: 1.33 s earlier) |
| 2 | Missed note C#5 (silenced) | 16, beat 2.5 | 42.05-42.33 s | 40.72-41.00 s |

## Results

Run on main 1e81bac (the commit these takes branch from), server `AI_ENABLED=false` (feedback mode `fallback`), 2026-10-11. For each run I called `backend/scripts/e2e_real.py`'s own functions from a throwaway wrapper (not committed) so I could keep the full analysis JSON; the steps and requests are the script's. Server on port 8137 because 8000 was taken on this machine. Score and bars: Ode to Joy `testdata/ode_to_joy/score.musicxml --bars 1-16 --bpm 100`; video1 `trumpet_video1_sheet.webp --bars 1-16` (scanned tempo 90); video2 `trumpet_video2_sheet.webp --bars 1-20` (scanned tempo 90). Every run: take status `done`, `form_status` `done`.

"Found" = the designed mistake is in the app's note list exactly (right bar, note and status). "Missed" = a designed mistake the app didn't report. "Extra" = something the app reported that I did not put in and the unmodified baseline doesn't report either (a relabelled baseline problem is called out as such). Baseline problems come from the unmodified source (rows marked baseline), so they are not mistakes of mine.

| Take | Align | ok / wrong / missed | Extras | Found | Missed (not reported) | Extra (not designed, not in baseline) |
|---|---|---|---|---|---|---|
| Ode to Joy, baseline | 1.000 | 62 / 0 / 0 | 1 (bar 4, A4, 11.63 s) | - | - | - |
| ode_to_joy_wrong_note | 0.968 | 60 / 2 / 0 | 1 (same as baseline) | both: bar 3 A4 heard G#4 (-105 cents); bar 14 C5 heard C#5 (+95 cents) | none | none |
| ode_to_joy_missed_and_rushing | 0.984 | 61 / 0 / 1 | 2 | missed bar 11 B4 (exact); rushing, see below | none | one extra G4 in bar 8 (18.78 s); the baseline's A4 extra now sits in bar 5 (11.62 s, same note) |
| video1, baseline | 0.981 | 102 / 0 / 2 | 11 | - | - | - |
| trumpet_video1_wrong_note | 0.962 | 100 / 2 / 2 | 11 (same as baseline) | both: bar 3 A4 heard G#4 (-110 cents); bar 13 G5 heard G#5 (+125 cents) | none | none |
| trumpet_video1_missed_and_rushing | 0.962 | 100 / 1 / 3 | 10 | missed bar 14 D5 (exact) | rushing not reported (see below) | missed bar 1 A#4 and bar 16 A3; bar 16 G3 reported wrong (heard A3); one extra G3 (bar 16, 58.86 s) |
| video2, baseline | 0.983 | 119 / 0 / 2 | 4 | - | - | - |
| trumpet_video2_wrong_note | 0.967 | 117 / 2 / 2 | 4 (same as baseline) | both: bar 6 A#4 heard B4 (+117 cents); bar 9 B3 heard A#3 (-90 cents) | none | none |
| trumpet_video2_missed_and_rushing | 0.950 | 115 / 0 / 6 | 3 | missed bar 16 C#5 (exact); rushing reported over bars 1-8 | none (bars 5-8 is inside the reported bars 1-8) | missed bar 5 C#5 (beat 1.5), bar 11 D#4 (beat 2.5), bar 15 C#5 (beat 3) |

Baseline problems that stay (not mine): video1 missed bar 10 D5 and bar 12 G4 (both baseline-missed; in the missed_and_rushing take they are no longer reported, and the three extra misses above appear instead); video2 missed bar 3 A#4 and bar 9 G#4 (bar 3's miss moves from the second to the first of two same-pitch A#4 notes, bar 3 beat 3.5, in the rushed take: the same event relabelled; bar 9's stays).

What the app said about the rushing (the missed_and_rushing takes)
- Ode to Joy: played tempo 104.8 BPM (baseline 100.06). Problem "rushing, bars 5-7, 14.66% faster than 100 BPM" (tier 2): the injected 15% over bars 5-8, found with the right size, one bar short. Tier 1 headlines instead: "Bars 7-12: 20 notes early, 258 ms on average", "Bars 2-6: 15 notes late, 208 ms on average" (my reading, not verified: it takes the shift after the phrase for early notes and the phrase's start for late ones), and a tier-2 "dragging, bar 8, 32.58% slower" (bar 8 follows the speed-up; wrong direction).
- video1: no rushing problem at all. The player is about 28% slower than the written 90 BPM, so even 15% faster (about 74 BPM) is still slow; the app reports "dragging bars 1-16, 26.8%" and, as in the baseline, early/late timing sentences ("Bars 6-13: 46 notes early, 519 ms", "Bars 1-5: 25 notes late, 404 ms"; baseline had 244 ms and 341 ms), so the injected shift shows as larger timing errors, not as rushing.
- video2: played 97.2 BPM (baseline 93.99). Tier-1 "Bars 1-8: rushing, about 18% faster than 90 BPM" (17.68%): the baseline already rushes bars 1-2 (11.8%), so this is the injected phrase plus the baseline start, with the bar range starting at 1 not 5. Also tier-1 "Bars 1-6: 28 notes late, 272 ms", "Bars 15-19: 29 notes late, 188 ms" and tier-2 "Bars 7-12: 377 ms early" (the phrase's shift read as timing errors).

What the app said about the wrong notes (the wrong_note takes)
- Ode to Joy: tier-1 "Bars 3-4: 1 wrong note (played G#4 for A4) and 1 extra." (the extra is the baseline's); the second wrong note (bar 14, C#5 for C5) is a tier-2 problem.
- video1 and video2: both wrong notes are tier-2 (video1) or tier-3 (video2) problems with the right played/expected pitches, behind the baseline's tempo and timing sentences. The tier-1 sentences are the same as the baseline's.

Guesses, not verified
- The extra misses and the wrong G3 in the rushed takes of video1 and video2, and the extra G4 in Ode to Joy bar 8, are on notes I did not edit (apart from the time shift). Several are in same-pitch runs (Ode to Joy bar 8 G4 G4, video2 C#5 repeats, video2 bar 11 D#4 D#4), so they may come from the transcriber's same-pitch splitting or from the alignment slipping by one note after the shift; I did not look into which.
- The elbow-pinned form flags appear on the Ode to Joy baseline and both its takes, so they are not caused by these edits; video1 and video2 raise no form flags in any run (checked in the run output).
