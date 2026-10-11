---
urgency: ride-along
component: backend
audience: internal
---
Demo-day check of the trumpet flow on main e7064b3 with AI_ENABLED=false: every route answered correctly and no code fix was needed.

## How it was run (2026-10-11)

- `backend/.venv` (Python 3.12.x, `pip install -r backend/requirements.txt`), `uvicorn app.main:app` on 127.0.0.1:8000, no keys, no AWS. Driven only over HTTP by a script that is not in the repo.
- ffmpeg is not on this Mac's PATH, but the backend uses the bundled `imageio-ffmpeg` binary, so nothing needed it from outside. Environment gap: none.
- Cold start: the first `uvicorn` start took about 25 s before it answered (imports of homr, mediapipe, librosa). Warm starts were not timed.
- Run A: `trumpet_video1_sheet.webp` + `trumpet_video1.mp4` (bars 1-8). Run B: `ode_to_joy_photo.jpg` + `ode_to_joy/ode_to_joy_trumpet11.mp4` (bars 1-16). Run C: `ode_to_joy/score.musicxml` through `/score/file` + the same video (the matching score), plus error-path calls.

## Steps

| Step | Route | Status | Time | Verdict | Note |
|---|---|---|---|---|---|
| Create session | POST /sessions | 201 | <0.1 s | OK | |
| Scan upload | POST /sessions/{id}/score/photo | 202 | <0.1 s | OK | `scanning` |
| Scan poll | GET /sessions/{id}/score/status | 200 | A 17.4 s, B 5.0 s | slow (A) | `scanned`, 16 bars. A is the first homr run in the process (cold); B on the same server took 5 s |
| Confirm | POST /sessions/{id}/score/confirm | 200 | <0.1 s | OK | 16 bars, tempo 90 |
| Read score | GET /sessions/{id}/score?format=json | 200 | <0.1 s | OK | 16 bars |
| Score from file | POST /sessions/{id}/score/file | 200 | <0.1 s | OK | musicxml, tempo 100 |
| Take upload | POST /sessions/{id}/takes | 202 | <0.1 s | OK | video/mp4 (an unsupported or guessed mime gives 415 `unsupported_type`, a clear message) |
| Analysis poll | GET .../takes/{tid}/analysis | 200 | A 30.7 s, B 13.1 s, C under 25 s | slow | `done`, form `done`. Notes ready (`diagnosed`) at 10.6 s in A and 3.0 s in B; the rest is form tracking. A: alignment 1.0, 7 problems. B: `cant_tell` (alignment 0.016) because the scanned photo score does not match that video, an expected mismatch. C: alignment 1.0 |
| Tracks | GET .../takes/{tid}/tracks | 200 | 0.1 s | OK | |
| Take media | GET .../takes/{tid}/media | 200 | <0.1 s | OK | video/mp4 |
| Feedback + plan | POST and GET .../takes/{tid}/feedback | 200 | <0.1 s | OK | `mode=fallback`, `fallback_reason=disabled`, 4 plan exercises (A), 1 (B); same body on repeat |
| Trace | GET /sessions/{id}/feedback/{fid}/trace | 200 | <0.1 s | OK | 1 event: orchestrator `fallback` "disabled" |
| Progress before | GET /sessions/{id}/progress | 200 | <0.1 s | OK | A: `before` filled, `after` null. B: `before` null (cant_tell take) |
| Exercise | GET /sessions/{id}/exercises/{eid} | 200 | <0.1 s | OK | |
| Rep upload | POST .../exercises/{eid}/reps | 202 | <0.1 s | OK | `processing` |
| Rep poll | GET .../reps/{rid} | 200 | 2.5 s | OK | A: `scored`, 8 errors, not passed, `next_bpm` 62. B: `not_counted` ("could not line up this rep with bars 1-16"), consistent with the cant_tell take |
| Progress after | GET /sessions/{id}/progress | 200 | <0.1 s | OK | A: `after` filled from the rep (`source: rep`) |
| Error paths | feedback / trace / exercise / rep with unknown ids; feedback while the take is processing; transposition change | 404 / 409 / 200 | <0.1 s | OK | JSON `{"error":{"code","message"}}` each time: `take_not_found`, `feedback_not_found`, `exercise_not_found`, `rep_not_found`, `wrong_state`. POST /sessions/{id}/transposition returned 200 with `rerun_takes: ["t1"]` |

Server log: no 5xx and no traceback over the three runs; the only 4xx were the error paths above and the 415 from curl guessing the wrong mime.

## Slow (over 10 s)

- Analysis poll, 13 to 31 s for a 64 s video: mostly pose tracking after the notes are ready. The UI polls, so it is waiting time, not a failure.
- First scan after start, 17 s (5 s warm); first server start, about 25 s.

## Bugs for other teams

None found.

## Fixes

None needed in `backend/app/agents/` or the feedback and trace routes.
