# Integration check, AI off

## 2026-10-10: main 3d970aa (AI_ENABLED=false)

Main was 3d970aa ("Measure cheekPuff and cheek width on the cheek modulation clip") = origin/main after `git fetch`.
Fresh `backend/.venv` created in the worktree, `pip install -r backend/requirements.txt`.

### On main
- Front end (LLD-7) is on main: latest `frontend/` commits include "Results: don't render after the user left during the feedback request", "Results: write the feedback again after a hand-made transposition change", "Auto key: wait for the rerun to finish, retry a 409 from the feedback request", "Results: automatically find the transposition for a low_match can't-tell take", "Router: decode URL params safely...", "Calibration: ... Try again ... (FE-4, FE-16)", "Camera guide: front/side view picker, side outline and badge, side-only results overlay", "Take screen: stop the recorder when leaving or failing to start (FE-6, FE-7)", "Tone page: Stop button, 10 s auto-stop...", "Frontend: one shared retry queue ... (FE-3)".
- Practice loop (LLD-6) is on main: `backend/app/practice/` commits: "Sweep stale practice reps when a new rep is claimed (LLD-6 change 4)", "Add rep, exercise and progress routes (LLD-6 change 3)", "Do practice progress read-modify-write inside store.modify under the session lock", "Score practice reps and run the tempo ladder (LLD-6 change 2)", "Import note statuses from diagnosis config in practice rules", "Add practice pass mark and tempo ladder rules", "Add back-end skeleton: FastAPI app, session store, error format, tests, testdata" (only 7 commits touch it).

### Test suite
- `backend/.venv/Scripts/python -m pytest backend/tests -q`: **1074 passed, 11 skipped, 0 failed** (269.75 s), exit 0.
- Noise after the summary: a mediapipe teardown `TypeError: 'NoneType' object is not callable` (mediapipe_c_utils.py line 126, via shutdown_aware_handler) printed at interpreter exit; it does not change the exit code.
- E2E: `RUN_E2E=1 pytest backend/tests/test_e2e_trumpet_flow.py -q`: **9 passed** (299 s). Note it uses trumpet_video1 + its sheet photo, not ode_to_joy.

### Front end walk (uvicorn 0.0.0.0:8020, port 8000 was taken; browser at http://127.0.0.1:8020/)
The browser tools here have no file-upload handler, so the file chooser opened by "Choose File" could not be answered (it left tab 0 stuck on a modal). Uploads of the score and the take were therefore done with curl against the same API the front end calls (same `POST /sessions/{id}/score/file`, `/score/confirm`, `/takes` fields as `takeFields`), then the browser was pointed at that session (localStorage key `practice_coach_session_id`, set by a temporary helper page that was deleted afterwards) and opened `#/results/t1`.

| Step | Result | Detail |
|---|---|---|
| Load `/` | ok | Redirects to `#/start`, nav and Start button show |
| Start session | ok | `POST /sessions` 201 |
| Score: Built-in tab, Use Ode to Joy, Confirm | ok | "16 bars found." Note: the built-in (tempo 96, first written note F#4) does not match ode_to_joy_trumpet11.mp4: a take against it gave `cant_tell` `low_match`, alignment_quality 0.097 (expected mismatch, not a bug) |
| Score: upload testdata/ode_to_joy/score.musicxml | ok (via curl) | 16 bars, tempo 100, transpose -2 |
| Calibrate screen / Skip calibration | ok | QR + tone notes show; Skip goes to `#/take`. Recording the notes needs a mic: not tried |
| Take screen: choose bars, tempo, mic/video | ok | Bars 1-16, tempo follows the score (100), count-in defaults to 4 |
| Take: Record (video mode) | ok (graceful) | Headless browser has no camera/mic: shows "Chrome is blocking the mic. The app cannot record without it." with Try again / Upload a recording instead. Console: 2 errors (not captured, presumably the denied getUserMedia) |
| Take: file upload of ode_to_joy_trumpet11.mp4 | not tested in the browser | No file-upload tool; done by curl with bar 1-16, tempo 100, count-in 0 |
| Analysis | ok | status `done`, form_status `done` within about 1 minute; alignment_quality 1.0, cant_tell false, played 100.06 bpm |
| Results: note results / bars heatmap | ok | "What I measured" and "Bars to work on" lists (Bar 8 rushing +5.12%, Bar 9, Bar 4 1 extra, Bar 5). No coloured grid heatmap was visible in the accessibility snapshot; not checked visually |
| Results: form results | ok | Video with "Show body lines" and two "right elbow pinned to the body" events at 14.5 s and 24.1 s. Camera-view picker (front/side) was not on the results page and was not reachable (needs a camera) |
| Results: coach panel (AI off) | ok | "AI coach unavailable; showing measured results." and Instructor panel "AI instructor unavailable" with 3 checked measured sentences |
| Results: practice plan | ok | 4 exercises. Cosmetic: every plan says "from 100 to 100 bpm" (start equals target because the take was already at target) |
| Exercise `#/exercise/ex1` | ok | Title, rule, tempo 100, 0 of 2 passes, "Record rep" button. Recording a rep not tried (needs mic) |
| Progress `#/progress` | ok | Before/after table, 4 exercises "In progress" |
| Trace `#/trace/fb1` | ok | "The AI could not be used, so the safe built-in text was shown." Orchestrator row "fell back to the safe text disabled" |
| Camera check | not tested | No camera in the test browser |
| Top navigation links | cosmetic | Header links point at placeholder ids (`#/results/take_1`, `#/exercise/ex_1`, `#/trace/fb_1`) that do not exist for a real session |
| Server log | ok | No 5xx or tracebacks; the only 4xx were two 409 `wrong_state` I caused by re-posting a score to a confirmed session |

Observed, front-end driven: with the mismatched built-in score, opening results on a low_match take made the front end automatically change the session transposition (-2 -> -6 -> -7 in the log, back to -2 on a later take). The session's transposition was left changed by a take the user did not ask to change; worth a look if that is not intended.

## r4-D feedback after key rerun (2026-10-11)

Main 0480972, `AI_ENABLED=false` (feedback mode `fallback`, no Bedrock). Real flow through the FastAPI TestClient (throwaway driver, not committed): Trumpet session, `testdata/ode_to_joy/score.musicxml` (file transpose -2), `testdata/ode_to_joy/ode_to_joy_trumpet11.mp4` as a take (bars 1-16, tempo 100, count-in 0), wait for `done`, read GET analysis and GET feedback, then `POST /sessions/{id}/transposition {"semitones": 0}` (detected/file value was -2), wait for the rerun, read both again. (The take is concert pitch; the detected value here was -2 from the file, not -4.)

**Verdict: FAIL. Feedback is not rebuilt after the rerun (BE-18 still open).** LLD-5 needs raising.

| | Before (transposition -2, source file) | After (transposition 0, source user) |
|---|---|---|
| Analysis | alignment_quality 1.0, 3 problems: `p:t1:0` notes bar 4 (1 extra, tier 1); two form problems (tier 2) | alignment_quality 0.5, `p:t1:0` notes bars 1-16 (18 wrong, 13 missed, 14 extra, tier 2), rushing bars 4-5, dragging bars 2-3, early bars 10-11, ... |
| Analysis `tier1` | `["Bar 4: 1 extra."]` | `[]` |
| Feedback (GET) | `fb1`, tier1 `"Bar 4: 1 extra."` (cites `p:t1:0`), plan `pl1` | **unchanged: same `fb1`, same `created_at`, same tier1 `"Bar 4: 1 extra."`, same plan `pl1` (exercise "Work on bars 4 to 4")** |

After the rerun the feedback still cites `p:t1:0`, but that id now names a different problem (bars 1-16, tier 2), so the sentence describes the old diagnosis, and the plan still drills bar 4.

Where the rebuild is missing: `backend/app/diagnosis/routes.py::set_transposition` queues `backend/app/diagnosis/rerun.py::rerun_takes`, which calls only `app.diagnosis.run(session_id, take_id)`. Nothing calls `app.agents.run.run_feedback` afterwards. Its only callers are `takes/pipeline.py::_give_feedback` (first processing of a take) and `POST /sessions/{id}/takes/{take_id}/feedback` (`agents/routes.py::rerun_feedback`). Today only the front end ("Results: write the feedback again after a hand-made transposition change") refreshes it, by calling that POST; a client that does not, or a rerun with the page closed, keeps stale feedback and plan.

Test: `backend/tests/test_integration_rerun_feedback.py` (0.6 s, synthetic notes, no media) asserts the rebuilt feedback (new id, tier-1 problem ids all in the new diagnosis, tier-1 text changed). It is `xfail(strict=True)` and fails on `assert 'fb1' != 'fb1'`; it turns into an error, so the marker must be removed, once the rebuild exists. No app code was changed.
