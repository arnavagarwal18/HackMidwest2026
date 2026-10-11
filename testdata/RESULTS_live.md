# Live Bedrock results (TASK-28)

Date: 2026-10-11 (UTC). Commit tested: d9f69ff (origin/main). Model: Claude Haiku 4.5 (us.anthropic.claude-haiku-4-5-20251001-v1:0), us-east-1, profile hackmidwest.

| section | result |
|---|---|
| 0. Setup (.env, sts, venv) | PASS |
| 1. Smoke test | PASS |
| 2. Score referee on 2 phone photos | PASS for the outcome; the 0.7 floor was only exercised on the good photo |
| 3. Coach / Planner on the reference take | PASS |
| 4. Instructor chat | FAIL |

## Failures
1. Instructor chat: 2 of the 3 required questions ("Where did I rush?", "Which bar had the most wrong notes?") fell back with `model_error`; over 6 turns, 3 were AI. In every failure the model ended its turn with plain text instead of calling `submit_reply`, so the Checker never ran (section 4).
2. Score referee: the bad (blurry) photo never reaches the referee: homr returns no notes (`no_notes`) and the Score reader returns 0 bars, so the 0.7 floor was not tested on a bad read (section 2). The reader also returns 0-4 bars on the good multi-line photo and varies run to run, so the normal path skipped the referee there too.
3. Not a code failure: port 8002 was already held by someone else's uvicorn (PID 75677), so section 3 and 4 ran on 8003.

## 0. Setup: PASS
backend/.env written (git-ignored, not committed), backend/.venv built from requirements.txt + requirements-dev.txt, sts OK.

## 1. Smoke (`RUN_LIVE_BEDROCK=1 backend/.venv/bin/python scripts/live_bedrock_smoke.py`): PASS
Whole run 63.9 s wall, exit 0.

| step | result | seconds | checker | mode |
|---|---|---|---|---|
| settings | pass | - | n/a | - |
| score reader (vision) | pass | 4.6 | n/a | - |
| feedback: coach | pass | 11.4 | accepted | ai |
| feedback: planner | pass | 11.4 | accepted | ai |
| instructor chat | pass | 9.0 | accepted | ai |

Take analysis and feedback: 36.8 s (35 polls).

## 2. Score referee on the owner's 2 phone photos (floor 0.7, backend/app/score/referee/config.py): PASS for the outcome, but the 0.7 floor was only exercised on the GOOD photo
Photos are 1002x678 and 996x670 screenshots, read in place (not copied into the repo). Normal photo-read path = clean -> homr + Score reader -> compare_bars -> referee.run (same calls as scan_job.run_scan), run in a scratch script.

**GOOD (F-14):** homr read 28 bars / 132 notes (4/4, key 0). The reader (Haiku 4.5 vision, nondeterministic) gave a different answer each run on the same cleaned photo: 0 bars, then 1 bar ("E5 quarter x4", wrong), then 4 bars. Normal path therefore never called the referee: `skipped / nothing_to_check` (reader 0 bars, so no comparison) and `skipped / mostly_different` (reader 1 bar vs homr 28). Called directly with every bar marked doubtful (bars 1-20, the 20-bar cap), 35 s, status done, model haiku-4-5:
- bar 1: pick homr, confidence 0.85, accepted (the reader's "E5 quarter x4" was wrong; the referee said the photo shows rests and sixteenths).
- bars 2-15, 17-20: pick homr, confidence 0.90-0.95, accepted (these had no reader bar, so "homr passes the code checks").
- bar 16: pick neither, confidence 0.70, NOT accepted (rejected_because `neither`; homr's bar is 3.5 beats not 4.0).
So the floor kept every real ruling; the only one not applied was the length-check failure.

**BAD (F-13, blurry):** homr found no notes (`ScanError: cleaned.musicxml contains no notes`), so the scan fails with `no_notes` before the referee is reached. The reader returned 0 bars on 4 of 4 attempts (plus 2 more in a control run, cleaned and raw). With no homr score and no reading, the referee has nothing to rule on: calling it directly gives `skipped / nothing_to_check`, so no confidences exist.

**Verdict:** the good read is kept (all confidences >= 0.70 except bar 16, which is correctly refused). The bad photo is rejected, but by homr's `no_notes` failure, not by the 0.7 floor; the floor was not exercised on it, so this run does not prove the floor rejects a bad read.

Observations (not fixed, no code changes allowed): (a) the reader prompt asks for "a single line of printed music" and returns 0 to 4 bars on a multi-line page, and varies run to run, so on these photos it rarely gives homr a usable second opinion (control: the same reader returned 8 bars on testdata/ode_to_joy_photo.jpg, cleaned and raw); (b) a reader that returns 0 bars gives the "couldn't double-check" warning, and 1 bar gives "mostly different", so the referee is skipped either way.

## 3. Coach / Planner on the reference take (ode_to_joy_trumpet, ode_to_joy_trumpet11.mp4, bars 1-8): PASS
Server: uvicorn on **127.0.0.1:8003**, not 8002: port 8002 was already held by a uvicorn I did not start (PID 75677, up 24 min, left alone). Flow: POST /sessions (trumpet) -> POST /score/file {"builtin":"ode_to_joy_trumpet"} -> /score/confirm (16 bars, 96 bpm, 4/4) -> POST /takes (video, bars 1-8, tempo 96, count-in 0) -> poll /analysis -> GET /feedback -> GET /trace. Session 7ebb59f437dd4fc8b75c26f4a46e2b4f, take t1, feedback fb1, plan pl1.

Timings: take accepted 0.0 s; analysis done after 32.1 s (17 polls; feedback was already stored by then); the feedback run itself 14.7 s (`duration_ms` 14698); whole flow 32.2 s.

**Mode: ai, fallback_reason null, cant_tell false.** Checker: coach_tries 2, planner_tries 2, claims_checked 6, claims_failed 0, sentences_dropped 0.

Tier 1 problems found: "Bar 8: 1 extra." (jump 21.42 s) and "Bar 4: 1 extra." (jump 11.63 s). Take overview: 30 notes ok, played 100.1 bpm vs target 96.

**Coach text (3 sentences):**
1. "In bar 4, you played an extra A4 that wasn't written." (cites x:t1:15)
2. "In bar 8, you added another extra A4 where it doesn't belong."
3. "Count the beats carefully and tongue only the notes on the page."

**Plan pl1 (mode ai), 3 exercises**, all start 88 bpm, target 96, step 4, 2 reps to pass:
1. "Bar 4 Extra Note Control": bars 3-5, max_errors 0.
2. "Bar 8 Posture and Precision": bars 7-8, form_rule `slouching`, max_errors 0.
3. "Full Range Integration": bars 1-8, max_errors 1.

**Checker verdicts in the trace (62 events, mode ai):**
- coach try 1 (t=9.1 s): `check_fail`, 2 problems, first "count mismatch: x:t1:15 has no stored extra count".
- planner try 1 (t=11.0 s): `check_fail`, 3 problems, first "bad tempo: start 100.12 BPM must be 30 to target 96 BPM".
- coach try 2 (t=11.4 s): `check_pass`, 6 claims checked.
- planner try 2 (t=14.1 s): `check_pass`, 0 claims checked.
Orchestrator finished at 14.7 s. Both agents ran in parallel after the orchestrator's get_take_overview call, and each fixed its answer from the Checker's reason on the second try.

Note (not fixed): the 3-exercise plan's exercise 2 uses a posture form rule (slouching) for bar 8 though the Coach's only problems are extra notes; I did not check where that form rule came from.

## 4. Instructor chat: FAIL (2 of the 3 required questions fell back; 3 of 6 turns were AI in total)
Commit tested: d9f69ff. TEAM-12's Instructor chat (TASK-21) is already on origin/main (849e730 "Add the Instructor chat" and the follow-ups up to 82ff6a3), so no pull was needed; uvicorn was started after the pull, on 127.0.0.1:8003. Same session and take as section 3 (7ebb59f4..., take t1). POST /sessions/{id}/chat.

| question | time | mode | fallback_reason | answer | cites a bar or time? |
|---|---|---|---|---|---|
| "What should I fix first?" | 8.2 s | ai | - | "Fix the extra notes first: you played an extra A4 in bar 4 and bar 8. Then work on your posture - slouching in bars 1, 3, 7, and 8." | yes: bars 4, 8 (measurements x:t1:15, x:t1:31) and form flags f:t1:1-3 (bars 1, 3, 7, 8; with time_s on the claim) |
| "Where did I rush?" | 3.3 s | fallback | model_error | "The AI instructor is unavailable right now. Here is what was measured: Bar 8: 1 extra. Bar 4: 1 extra." | jump to bars 8 and 4 (time_s null); the text answers a different question |
| "Which bar had the most wrong notes?" | 2.1 s | fallback | model_error | same fallback text | jump to bars 8 and 4 (time_s null) |

Cause (read from the saved traces, c4/c6): in both fallbacks the model ended its turn with a plain-text answer (`end_turn`) instead of calling the `submit_reply` tool, so the Checker never saw it and the reply became `fallback / model_error`. The discarded texts were reasonable ("You didn't rush - you played 100 BPM against the target 96" and "Bar 8 had the most wrong notes - 1 extra note"). The server log only says "The instructor replies in fallback mode (model_error)", with no hint of this cause.

Repeat run, same 3 questions, same session (extra, to see if it is flaky): fix-first fallback (model_error), rushed fallback (model_error), most-wrong-notes ai ("Bar 8 had the most wrong notes - you played 1 extra note there. Bar 4 also had 1 extra note. Fix bar 8 first ..."). Traces again show plain `end_turn` text with no submit_reply on the failures. Overall 3 of 6 turns used the AI; when the model does call submit_reply the Checker passes it (try 2 on the first turn, try 1 later).

Note (not fixed, no code changes allowed): the smoke test's one chat turn (section 1) passed with ai mode, so a one-turn smoke hides this rate.

## Sonnet 4.6 vs Haiku 4.5 (TASK-29): DECISION: stayed on Haiku 4.5
Date: 2026-10-11 (UTC). Commit tested: 3793932. Sonnet 4.6 profile: `us.anthropic.claude-sonnet-4-6` (text + image, used for both BEDROCK_TEXT_MODEL and BEDROCK_VISION_MODEL). `list-inference-profiles` is AccessDenied for this role (IAM), so the ID came from `list-foundation-models` (`anthropic.claude-sonnet-4-6`, TEXT+IMAGE) and was verified by one converse call (867 ms, 20 tokens, no retries). Haiku 4.5 figures are from the sections above.

| step | Haiku 4.5 | Sonnet 4.6 |
|---|---|---|
| smoke: score reader (vision) | 4.6 s | 11.3 s |
| smoke: coach / planner (ai, accepted) | 11.4 s | 21.6 s |
| smoke: chat (ai, accepted) | 9.0 s | 8.8 s |
| smoke total (analysis + feedback) | 63.9 s run, 36.8 s analysis | 48.8 s analysis |
| live_check (`python -m app.agents.live_check`) | not recorded | OK, 18.4 s total; coach 12.1 s, planner 14.5 s; Checker rejected 4 coach sentences / 1 exercise on try 1 |
| HTTP flow: feedback run (ode_to_joy_trumpet, trumpet11.mp4, bars 1-8) | 14.7 s, mode ai, Checker 2nd try (coach and planner) | 22.3 s, mode ai, fallback_reason null, Checker 2nd try (coach and planner) |
| HTTP flow: analysis done | 32.1 s | 38.0 s |
| chat "What should I fix first?" | 8.2 s, ai | 11.1 s, ai (submit_reply called twice; both tries failed the Checker, 2 of 3 sentences dropped, 1 kept) |
| chat "Where did I rush?" | 3.3 s, fallback model_error | 2.9 s, fallback model_error (no submit_reply: model ended with text after list_problems / list_form_flags) |
| chat "Which bar had the most wrong notes?" | 2.1 s, fallback model_error | 3.7 s, ai (submit_reply called, Checker passed 1st try) |
| chat turns with AI mode | 1 of 3 (3 of 6 over two runs) | 2 of 3 |
| chat turns where the model called submit_reply | 1 of 3 | 2 of 3 |

Sonnet feedback text (ai): bar 4 and bar 8 extra A4 plus slouching in bars 1, 3, 7-8; plan ai with 3 exercises. Session afaad22eaae046698230feca450cfb3d, take t1, fb1.

Verdict criteria: smoke passes (yes), feedback mode=ai (yes), feedback agent run under the 30 s limit (22.3 s, yes), no step over its limit (yes; reader 11.3 s is under its 30 s limit). The criteria were met, but the owner decided against the switch (below). Cost: every AI step is roughly 1.5-2.5x slower. Not fixed by the model: chat still falls back when the model ends with plain text instead of calling `submit_reply` (1 of 3 here), and one chat answer in each run ("zero wrong notes" next to "extra notes in bars 4 and 8") passed the Checker while contradicting itself.

**Chat rerun on main with TEAM-12's submit_reply fix (f988c03 is an ancestor; run in-process with FastAPI TestClient, so no server was left running; feedback run 23.3 s ai, analysis 39.1 s):**

| question | time | mode | submit_reply called / Checker |
|---|---|---|---|
| "What should I fix first?" | 8.0 s | ai | called, passed 1st try (4 claims) |
| "Where did I rush?" | 5.0 s | fallback `checker_rejected` | called twice; both tries failed ("uncited: a sentence must cite at least one measurement"), then fallback |
| "Which bar had the most wrong notes?" | 5.6 s | ai | called, passed 1st try (5 claims) |

After the fix every turn reaches submit_reply (Sonnet: 3 of 3; the 2 fallbacks before it were plain-text `model_error`), and the one fallback is now the Checker rejecting an uncited answer. AI mode 2 of 3 on Sonnet. TEAM-12's own Haiku 4.5 run after the fix: 10 of 10 ai, 2.5-7.1 s (reported by TEAM-12, not re-run here), so Haiku is currently more reliable and faster on chat; the switch rests on the owner's request (H-214/H-215) and the criteria above.

Deviation: `backend/app/agents/config.py` has no model defaults and `test_enabled_without_required_setting_names_it` requires a ConfigError for an empty model setting, so the default lives in `backend/.env.example` (Haiku 4.5 IDs, Sonnet 4.6 ID in a comment as a one-line swap). Full suite with Sonnet in `.env`: 1278 passed, 13 skipped (256.9 s).

**Decision: Stayed on Haiku 4.5 (owner, 2026-10-11): chat 10/10 ai after f988c03 vs Sonnet 2/3; Sonnet ~2x slower on Coach/Planner (21.6–23.3 s, near the 30 s limit).**
