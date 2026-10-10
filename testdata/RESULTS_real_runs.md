# Real-data end-to-end runs on main 3250d86 (2026-10-10)

Server: `AI_ENABLED=false uvicorn app.main:app --app-dir backend --port 8000`. All runs: `python backend/scripts/e2e_real.py <score> <video> ...`; status done, no errors. Feedback mode was `fallback` (reason `disabled`) in every run, so the tier-1 sentences are the rule-written ones. I read `outside_count` and the sentence jumps with a throwaway wrapper around the script's own functions (not committed).
"Jump" = the sentence's `jump.bar` is set; the bar's `time_s` is on the matching tier-1 item, and is null on the sentence itself. Every sentence cites one problem id (`p:t1:n`).

| Run | Align | ok / wrong / missed | Extras / outside | Played vs score bpm | form_status |
|---|---|---|---|---|---|
| 1a video1, `--bars 1-16` | 0.952 | 99 / 0 / 5 (104 notes) | 8 / 0 | 63.8 vs 90 | done |
| 1b video1, default bars (1-8) | 0.932 | 41 / 0 / 3 (44) | 6 / 62 | 65.6 vs 90 | done |
| 2 video2, `--bars 1-20` | 0.959 | 116 / 0 / 5 (121) | 1 / 0 | 93.9 vs 90 | done |
| 3 Hot Cross Buns `score.musicxml`, `--bpm 83` | 0.941 | 16 / 1 / 0 (17) | 0 / 0 | 83.6 vs 83 | failed (21 of 134 frames tracked) |
| 4 owner's Bb file, `--bars 1-5 --bpm 83` | 0.706 | 12 / 2 / 3 (17) | 2 / 1 | 114.3 vs 83 | failed |

Commands: run 1 `trumpet_video1_sheet.webp trumpet_video1.mp4 [--bars 1-16]`; run 2 `trumpet_video2_sheet.webp trumpet_video2.mp4 --bars 1-20`; run 3 `testdata/hot_cross_buns/score.musicxml "<Downloads>\Hot Cross Buns - Trumpet - DigiTide Blaze (1080p).mp4" --bpm 83`; run 4 the owner's `F-7-Hot_Cross_Buns_Bb_Trumpet.musicxml` with the same video, `--bars 1-5 --bpm 83`.

## Tier-1 sentences (all have a jump bar and one cite)
- 1a: "Bars 1-16: dragging, about 28% slower than 90 BPM." (bar 1) | "Bars 5-13: 44 notes early, 246 ms on average." (bar 5) | "Bars 1-3: 13 notes late, 337 ms on average." (bar 1)
- 1b: "Bars 1-8: dragging, about 28% slower than 90 BPM." (bar 1) | "Bars 7-8: 7 notes late, 212 ms on average." (bar 7) | "Bars 5-7: 12 notes early, 130 ms on average." (bar 5)
- 2: "Bar 1: 5 notes late, 214 ms on average." (bar 1) | "Bars 12-16: rushing, about 9% faster than 90 BPM." (bar 12) | "Bars 13-14: 8 notes late, 144 ms on average." (bar 13)
- 3: "Bar 3: 2 notes late, 113 ms on average." (bar 3) | "Bar 3: rushing, about 10% faster than 83 BPM." (bar 3)
- 4: none. 6 problems were found but none passed the tier-1 certainty/score floor (0.6 / 0.15); `tier1` and `sentences` are empty.

## Against the baselines (7800c54)
- Video1: the wrong notes are gone (0 wrong, was 11), alignment 0.636 to 0.95. Played tempo is still slow: 64-66 vs 90 bpm (was about 60). Bars 1-8 only (1b): the 62 notes beyond bar 8 are now outside, not extras (was 64 extras).
- Video2: 0.936 to 0.959, 0 wrong; the 63 extras (all in bar 8) are gone, 1 extra left (bar 12).
- Run 3: unchanged from before (0.94, 16 ok, 1 wrong: bar 3 C4 heard as C#4, +52 cents).

## Video1 wrong notes
There are none on 3250d86, so there are no played/expected pairs to classify as octave (12 semitones) or transposition (2 semitones). The earlier errors (e.g. D#5 for D#4) did not recur. Guess (not verified): the changes since 7800c54 (scan or pitch/octave handling) fixed them; I did not run 7800c54 to check. Remaining video1 misses: D5 (bar 1), A#4 (bars 3 and 5), D5 (bar 10), G4 (bar 12).

## Run 4: why it is weak
Inference from reading the file, not verified by a fix: the owner's file is a 5-bar arrangement (written E D C | E D C | C C C C | D D D D | E D C, quarters), while the video plays a 4-bar version (bar 3 is eight eighths, bar 4 is D C Bb). The score and the performance have different note counts, so alignment drops, the played tempo reads 114 vs 83, and the notes are wrong or missed (bar 1: expected D4 heard C4; bar 3 A#3 missed; bar 4 C4 heard C#4; bar 5 D4 missed). This is probably a mismatch between file and video, not a bug.
Runs 3 and 4 `form_status: failed` (same video): the log shows only "Tracked 21 of 134 frames"; I did not find the reason.

## Ode to Joy (lipslur.com, 2026-10-10, main 693bd32)
Source (not committed): `Trumpet 11 - Beethoven's 9th - Ode to Joy - lipslur.com (1080p).mp4` (43.5 s). Score `testdata/ode_to_joy/score.musicxml` (written from the app's own transcription of the audio; see `testdata/ode_to_joy/README.md`). Server `AI_ENABLED=false`; feedback mode `fallback` (reason `disabled`).
Command: `python backend/scripts/e2e_real.py testdata/ode_to_joy/score.musicxml "<Downloads>\Hacksmidwest Training Data\Trumpet 11 - Beethoven's 9th - Ode to Joy - lipslur.com (1080p).mp4" --bars 1-16 --bpm 100` (ran twice; the same numbers both times).

| Measure | Value |
|---|---|
| Alignment quality | 0.774 (target >= 0.8: not met) |
| Notes | 62 expected: 48 ok, 0 wrong, 14 missed |
| Extras / outside | 0 / 0 |
| Tempo | played 100.06 BPM vs score 100 (`clean_bpm` 70.04, exactly 70% of played; I did not check what it is for) |
| Tuning offset | none reported: `calibrated: false`, no offset field in the analysis. Per-note `cents_off` is -8 to +7 (the player is in tune, so nothing to correct) |
| Form analysis | ran, `form_status: done`; tracks returned (`tracking_quality` is null) |
| Transposition | -2 semitones, source `file` |

Tier-1 sentences: "Bars 8-16, 0:19: right elbow pinned to the body, at the same time as notes in bar 8." (bar 8) | "Bars 4-7, 0:11: right elbow pinned to the body, at the same time as notes in bar 4." (bar 4) | "Bars 1-9: 10 missed." (bar 1). Other problems: "Bars 13-16: 4 missed" and bar 8 rushing (5.9%), both tier 2.

False "wrong" notes: none (0 wrong; every heard pitch is in tune and the timing errors are under 60 ms).
False "missed" notes (all 14): each is the second note of a same-pitch pair (bars 1 n2, 2 n1, 3 n2, 4 n1 and n3, 5 n2, 6 n1, 7 n2, 8 n3, 9 n2, 13 n2, 14 n1, 15 n2, 16 n3: B B, D D, G G, A A, and a bar-ending A eighth into a held A, one of them across a barline). The player slurs, so the transcription gives one long note (e.g. 2.23-3.26 s for B B), and the scorer then reports the second note as missed. Guess (not verified): the transcriber only splits a repeated pitch when the level dips 3 dB (`ONSET_DIP_DB`), and this player's soft tonguing doesn't dip that much. This is also why alignment is 0.77 and why the "10 missed" tier-1 sentence is mostly false.
Form flags (not verified): "right elbow pinned to the body" covers bars 4-16 in two long spans, which looks like a camera-angle or pose-tracking artefact rather than a real fault; I did not look at the video frames.
