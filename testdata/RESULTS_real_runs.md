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

## After split fix (2026-10-11, branch task/TASK-27, `AI_ENABLED=false`, same commands as above)
Cause (verified on the Ode to Joy audio): the level does dip at every re-articulation, by 6.5-22 dB (median 13), but slowly (about 0.1 s to come back up), so the onset-strength peak is tiny (about 1.1 against 7 at the first attack) and `librosa.onset_detect` never fires there (e.g. no onset at 2.83 s, the second B). `ONSET_DIP_DB` (3 dB) is only checked at librosa onsets, so the dip was never looked at. Steady playing has under 2 dB of level movement.
Fix: `transcribe.py` also starts a new note at any level minimum at least `LEVEL_DIP_PROMINENCE_DB` (5 dB) deep (scipy `find_peaks`), merged with the onset-confirmed dips (`MERGE_SPLIT_FRAMES`).

| Take | Before | After |
|---|---|---|
| Ode to Joy, `--bars 1-16 --bpm 100` | 0.774, 48 ok / 0 wrong / 14 missed, 0 extras | 1.000, 62 ok / 0 / 0, 1 extra (bar 4); played 100.06 BPM |
| video1, `--bars 1-16` | 0.952, 99 / 0 / 5, 8 extras | 0.981, 102 ok / 0 wrong / 2 missed, 11 extras |
| video2, `--bars 1-20` | 0.959, 116 / 0 / 5, 1 extra | 0.983, 119 ok / 0 wrong / 2 missed, 4 extras |
| Hot Cross Buns, `--bpm 83` | 0.941, 16 ok / 1 wrong / 0 missed | 1.000, 17 ok / 0 / 0, 0 extras; `form_status` still failed |

Extras went up by 3 on video1 and video2 (more splits inside long notes); ok notes rose and missed notes fell on both. The "before" figures are from the earlier runs above (main 3250d86), not a rerun of debb837. Backend suite: 940 passed, 2 skipped.

## Real-video form checks at VIEW_SIDE_MAX 1.7 (2026-10-11)
`VIEW_SIDE_MAX` is 1.7, fitted on three clips (side 1.36, Ode 1.48, front 1.96). Numbers below are the previous worker's measurements; the view of the three `views` clips and the take5 front tracking/face thresholds were re-run on this branch (`AI_ENABLED=false`, all passing). Flag counts are not asserted by the tests.

| Clip | View (ratio) | tracking / face | Flags | Skipped rules | Time |
|---|---|---|---|---|---|
| `form/take5_ode_form_front.mp4` | front 1.957 | 1.0 / 1.0 | 10 (shoulders_raised x5, elbows_pinned x5) | none | 14.1 s |
| `form/take5_ode_form_side.mp4` | side 1.361 | 1.0 / 0.65 | none | slouching `not_visible`, elbows `not_for_view` | 16.9 s |
| `ode_to_joy/ode_to_joy_trumpet11.mp4` | side 1.479 | 0.949 / 0.947 | slouching at 1.8-3.1 s and 6.7-8.7 s | | 18.1 s |
| `trumpet_video1.mp4` | front 3.334 | | none | | 26.0 s |
| `trumpet_video2.mp4` | front 3.543 | | none | | 25.6 s |
| `form/bad_posture_example.mp4` | front 2.461 | 1.0 / | none | slouching and elbows `not_visible` | 3.5 s |

- The take5 side clip should be re-recorded with the hips in frame (slouching cannot be judged without them).
- The acted clip `form/bad_posture_example.mp4` currently flags nothing and has no fault times in `form_expectations.json`, so its test skips until Xavier or Caleb supplies the times.

Removed 2026-10-11: owner marked bad_posture_example.mp4 as bad data.

## r4 (2026-10-11, branch task/TASK-41, `AI_ENABLED=false`, port 8137, one fresh server per take)
Change: piecewise time map from pass 1's same-midi pairs (anchors off the line of their neighbours by more than 0.5 beat dropped), played-bars window, per-bar tempo against the take's own median tempo (+-7%), `tempo_vs_goal_pct`. Runs: Ode to Joy `score.musicxml --bars 1-16 --bpm 100`; video1 `trumpet_video1_sheet.webp --bars 1-16`; video2 `trumpet_video2_sheet.webp --bars 1-20`; take files from `testdata/mistakes/` and the unmodified recordings. "Before" = the ANSWER_KEY.md Results table (main 1e81bac). Every take: status done, `played_bars` = every asked bar, `not_played_count` 0 (all takes play the whole piece).

| Take | Align (before > after) | ok / wrong / missed after | Rushing (key: bars 5-8, 15%) | False-missed before > after |
|---|---|---|---|---|
| Ode baseline | 1.000 > 1.000 | 62 / 0 / 0 | none (right) | none |
| ode_wrong_note | 0.968 > 0.968 | 60 / 2 / 0 | none | none; both wrong notes found (bar 3, bar 14) |
| ode_missed_and_rushing | 0.984 > 0.984 | 61 / 0 / 1 | FOUND exactly: rushing bars 5-8, 12.0% (before: bars 5-7, 14.7%); bars 5-8 drift 13.4 / 12.8 / 11.9 / 9.9% | none; designed miss bar 11 B4 found; no more dragging on bar 8 |
| video1 baseline | 0.981 > 0.981 | 102 / 0 / 2 | n/a; bars 1, 3, 9, 11 read rushing 12-14% and bar 12 dragging 10% (the player is uneven) | baseline-missed bar 10, 12 unchanged |
| video1_wrong_note | 0.962 > 0.962 | 100 / 2 / 2 | n/a | same baseline misses; both wrong notes found (bar 3, bar 13) |
| video1_missed_and_rushing | 0.962 > 0.971 | 101 / 0 / 3 | PARTLY: rushing bars 5-6 (13.8 / 10.7%); bars 7-8 read steady (2.8 / 3.3%) | bar 1 A#4 (2nd) and bar 16 A3 > bar 1 only; the bar 16 G3 "wrong" and its extra G3 are gone; designed miss bar 14 D5 found; bar 10 is the baseline miss |
| video2 baseline | 0.983 > 0.983 | 119 / 0 / 2 | n/a (bar 1 rushing 9.5%, bar 12 dragging) | baseline-missed bar 3, 9 unchanged |
| video2_wrong_note | 0.967 > 0.967 | 117 / 2 / 2 | n/a | same baseline misses; both wrong notes found (bar 6, bar 9) |
| video2_missed_and_rushing | 0.950 > 0.950 | 115 / 0 / 6 | FOUND, one bar short: tier-1 "Bars 5-7: rushing, about 13% faster than your own tempo (96 BPM)" (bar 8 not flagged); before: bars 1-8, 18% against 90 BPM | bars 5 (C#5), 11 (D#4), 15 (C#5) > unchanged; bar 3, 9 baseline; designed miss bar 16 found |

Remaining false-missed notes: every one is the second note of a same-pitch repeat (video1 bar 1 A#4 A#4; video2 bar 5 C#5 C#5, bar 11 D#4 D#4, bar 15 C#5 C#5 C#5; also the baseline's video2 bars 3 and 9). The status is missed with no extra note beside it, and the baseline has the same pattern, so the cause is upstream of the alignment: the transcriber returns one note for the two repeated notes (inferred from this pattern; I did not inspect the transcription itself). The alignment now pairs the one played note with its own copy (video1 bar 16 is fixed), but it cannot invent the second note.

Not changed by r4 (found while checking): the tier-1 "N notes early / late, X ms" sentences still appear on every rushed take (e.g. video1 "Bars 6-13: 47 notes early, 521 ms"). `timing_ms` is still measured against the single fitted line, so the time saved by a sped-up phrase shows as early/late notes before and after it. The spec's time map is used for the alignment only. Bars 1-2 of video1 and the other uneven-bar drift problems (bars 10, 12, 13, 15, 16 dragging 9-17% in the rushed video1 take) come from the player's own uneven tempo against the median.
