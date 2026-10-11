# Xavier's X2-X5 checks with known answers

Run 2026-10-11 on Xavier's Windows laptop, main commit 15a5622, `AI_ENABLED=false`, server on 127.0.0.1:8003 (uvicorn from `backend/.venv`; stopped afterwards). One video at a time. Nothing pushed or merged.

## A. Planted mistakes (X4, X5, X2)

`backend/scripts/plant_mistakes.py` takes the clean reference recording `testdata/ode_to_joy/ode_to_joy_trumpet11.mp4` and its Trumpet in Bb score `testdata/ode_to_joy/score.musicxml` (16 bars, quarter = 100, the pair `RESULTS_live.md` and `RESULTS_integration.md` use). It places each note from the score at 100 BPM (first note matched to the take, each note snapped to the nearest sound onset, edits cut at the quiet point between notes) and writes `testdata/planted/ode_to_joy_planted.mp4` (git-ignored) plus `testdata/planted/answer_key.json`:

| # | Planted | Bar | Source time |
|---|---|---|---|
| 1 | wrong note: the G4 (beats 1-2 of bar 3, G G played as one) pitch-shifted down 2 semitones to F4 (up 2 gives A4, the neighbour's pitch, so it would not sound as its own note) | 3 | 6.97-8.15 s |
| 2 | missed note: C5 (beat 2) silenced | 6 | 14.78-15.33 s |
| 3 | rushing: audio and video of two bars time-compressed 15% | 9-10 | 21.31-26.13 s |

Everything after bar 10 plays 0.63 s earlier in the take. Mistakes are at least 2 bars apart.

Flow (as `backend/scripts/e2e_real.py`): create session, upload score file, confirm (16 bars, tempo 100, 4/4), upload take (bars 1-16, tempo 100, count-in 0), poll analysis (about 18 s, status `done`, alignment_quality 0.95, played 102.5 BPM), get feedback (with its plan), POST chat with take t1.

Diagnosis (`GET .../analysis`) against the key:
- Wrong note, bar 3: **flagged**. Two notes `wrong`, expected G4 played F4 (the app splits the G G pair into two notes); problem `p:t1:4` notes, bars 3-4, tier 2, `wrong: 2`.
- Missed note, bar 6: **flagged**. Note `n:t1:6:1` expected C5 `missed`; problem `p:t1:6` notes, bar 6, `missed: 1`, tier 2.
- Rushing, bars 9-10: **flagged**. Problem `p:t1:3` rushing, bars 9-10, `drift_pct` 15.04, tier 2 (bars 9 and 10 measure 17.5% and 12.6%).

Every other bar flagged (extras):
- `p:t1:0` late, bars 6-9, 13 notes, 198 ms (tier 1; the tempo shift after the missed note and the rushed bars)
- `p:t1:1` early, bars 10-12, 11 notes, 177 ms (tier 1; the take is 0.63 s early after the rushed phrase)
- `p:t1:2` early, bars 1-2, 7 notes, 137 ms (tier 1)
- `p:t1:5` late, bar 16, 2 notes, 90 ms (tier 2)
- extra note A4 at 11.63 s in bar 4 (inside `p:t1:4`; the clean recording gets "Bar 4: 1 extra" too, per `RESULTS_integration.md`)
- form `slouching`: bar 1 (1.6-3.8 s) and bars 2-4 (7.0-10.8 s), severity 0.02 and 0.01 (RESULTS_live.md's run of the clean recording shows elbow flags instead; not checked this time)
- Bar 3 and bar 6 are inside the flagged late/early ranges as well.

Feedback and plan (`mode: fallback`, reason `disabled`, as expected with AI off): the tier-1 sentences are the three timing problems above ("Bars 6-9: 13 notes late, 198 ms on average." and the other two). They do not name the wrong note, the missed note or the rushing: those are tier 2 and appear only in the diagnosis. The plan has 4 exercises: bars 6-9, bars 10-12, bars 1-2, and "Put it together" (bars 1-16); it does not name bar 3 or the rushing in bars 9-10. Chat (3 questions: "Where did I rush?", "Which bar had the most wrong notes?", "Which note did I miss?"): the same fallback answer to all three ("The AI instructor is unavailable right now. Here is what was measured: ..." with those three timing sentences), `mode: fallback`.

Note on the first run: the first version of the edit cut the missed note 40 ms short of the next note, leaving a 30 ms C5 blip that the app matched to the missed note as `ok` (confidence 0.21, 675 ms late). The script now cuts at the quiet point between notes; the figures above are from the second run (this fix is in the committed script).

## B. Posture faults (X3), `form.run` as a trumpet take (the test helpers `add_form_take` + `form.run`, whole video, AI off)

Keys are from `testdata/youtube/fault_keys.csv`; a flag of the same rule within the key's times plus its slack finds it.

| Video | Keyed fault | Flags found | Verdict |
|---|---|---|---|
| `EaTvWPsHDQ8` trumpet player - chair for best posture (78 s, side view) | head down and slouching, 53-64 s (slack 2 s). TASK-50 found both | `trumpet_head_down` 53.3-56.5 s (0.37), 57.2-58.9 s (0.10), 59.8-61.2 s (0.43); `slouching` 53.6-54.9 s (0.53), 61.5-64.4 s (0.22); also `trumpet_smile_embouchure` at 1.2-2.6, 3.7-5.9, 7.3-9.1, 9.9-12.9, 21.0-23.5 s (extras) | PASS |
| `z9YjzBBIF78` Playing Trumpet: How to Correct Puffed cheeks (50 s, front view) | head down, 41-49 s (slack 5 s; a hedged line: "head slightly lowered looking at the horn"). TASK-50 missed it | only `trumpet_smile_embouchure` at 17.3-18.7, 30.3-31.5, 43.6-44.6 s; no `trumpet_head_down`; the run's log skipped `slouching`, `trumpet_bell_angle`, `trumpet_elbows_pinned` and `trumpet_elbows_wide` (measure missing in over 70% of frames) and used the default head-drop baseline | FAIL |

Same flags as the 10 fps run in `testdata/youtube/fault_flags.csv` for `EaTvWPsHDQ8`. Videos fetched with `fetch_youtube.py --list testdata/youtube/fault_candidates.csv --only-group "3 Side bad"` and `--only-group "5 Puffed cheeks" --limit 1` (git-ignored in `testdata/youtube/fault_videos/`).

## C. X1 phone photo (run after the video jobs, same server on 8003, AI off)

Input: Xavier's phone photo of a screen showing a MuseScore page (attachment F-9, read from its attachment path, not copied into the repo). `POST /sessions/{id}/score/photo` on a new trumpet session, then polled `/score/status`.
- Scan time 37.4 s; `score_status` `scanned`, `score_error` null (no error code).
- Read: "The Star Spangled Banner", key_fifths -2 (2 flats), 3/4, tempo 90 (the app's default is also 90, so the tempo was probably not read from the page; not checked), 34 bars (key: about 33 +-2). Instrument "Voice".
- Doubtful bars: none. Referee `skipped` / `nothing_to_check`; warning "We couldn't double-check this scan: compare it with your copy before you confirm."
- Bar 1 (pickup) F4 dotted eighth + D4 sixteenth.
- Bar 2: Bb3 D4 F4, quarters: matches.
- Bar 3: Bb4 half, D5 dotted eighth, C5 sixteenth: pitches match (the key lists D5 C5 as quarters; the photo's rhythm was read by eye).
- Bar 4: Bb4 D4 E4 quarters; the key has Bb4 G4 E-natural: 2 of 3 notes match, the second is D4 not G4.
- Verdict: key, time signature and bar count are within the key's range and 2 of bars 2-4 match, so PASS.

XAVIER RESULTS (main commit 15a5622)
X1 phone photo: PASS - scanned in 37 s, status scanned, no error; key 2 flats, 3/4, tempo 90, 34 bars, no doubtful bars; bars 2 and 3 match (pitches), bar 4 has 2 of 3 notes
X2 confirm: PASS - score file uploaded and confirmed: 16 bars, tempo 100, 4/4 (a score file, not a photo scan)
X3 posture fault "head down and slouching 53-64 s" on EaTvWPsHDQ8 (found case): PASS - trumpet_head_down 53.3-56.5 s, 59.8-61.2 s; slouching 53.6-54.9 s, 61.5-64.4 s
X3b posture fault "head down 41-49 s (hedged)" on z9YjzBBIF78 (missed case): FAIL - no head_down flag; only trumpet_smile_embouchure 17.3, 30.3, 43.6 s
X4 note feedback: PASS - diagnosis names bar 3 wrong note (G4 played F4), bar 6 missed note (C5), bars 9-10 rushing (15.04%); planted bars 3, 6, 9-10; extras: late 6-9, early 10-12, early 1-2, late 16, bar 4 extra note, form slouching bars 1 and 2-4. The tier-1 feedback sentences name only the extras' timing problems, not the three planted ones
X5 plan/chat: PASS - mode fallback (AI off, reason disabled); plan of 4 exercises, chat answered by the same measured text to all 3 questions
