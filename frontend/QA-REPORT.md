# QA diagnostics report (HackMidwest2026)

Written 2026-10-10 against `origin/main` at c678f36. Doc only: no code was changed for this report. Backend findings come from a static review plus the stress run; per the owner's rule the backend was not edited.

## Summary

- All automated checks pass on c678f36: pytest 1014 passed / 11 skipped, `node --test` 141/141, `node --check` 0 failures on every front-end file.
- Stress run: 18,944 requests in 197 s at 20 concurrent, 0 hangs, 0 crashes. Large uploads work (200 MB OK, 201 MB gets 413).
- Browser check: 34 screen loads, all OK. Clicks (record, upload, playback, camera) were never exercised.
- Front end: 9 issues fixed and merged (FE-1, 2, 3, 4, 6, 7, 9, 16, 24); 6 medium and about 10 low issues are still open.
- Backend: 5 high and 6 medium findings (static review), plus 4 medium stress findings. Biggest risks: a global lock held across the Bedrock call (BE-3), no concurrency cap on photo scans (3.95 GB of child RSS from about 4 scans), and no auth/rate limit while bound to 0.0.0.0 (BE-10).
- Contract: of 29 front-end calls checked, only `GET /lan-address` has no backend route.

## Checks run, with results

Run on c678f36 (rebased main) on the Mac, 2026-10-10.

| Check | Command | Result |
|---|---|---|
| Backend tests | `.venv/bin/python -m pytest -q backend` (venv from `backend/requirements.txt`, Python 3.12) | 1014 passed, 11 skipped, 0 failed (107 s) |
| Front-end tests | `node --test frontend/tests/*.test.mjs` | 141 tests, 141 pass, 0 fail, 0 skipped. This includes `results.test.mjs`, which starts headless Chrome |
| Syntax check | `node --check` on every `.js`/`.mjs` under `frontend/` | 94 files, 0 failures (77 `.js` including `vendor/qrcode.js`, the rest `.mjs`) |

History (earlier diagnostics):

| Commit | Check | Result |
|---|---|---|
| 693bd32 | `node --check` | 84 files, 0 failures |
| 693bd32 | `node --test` | 105 tests, 103 pass; the 2 failures were FE-1/FE-2, since fixed |
| 9f983fa | pytest | 930 passed / 2 skipped |
| 48d6182, 7ac42c7, c678f36 | pytest | 1014 passed / 11 skipped |

Note: `dev/record-test.js` gives a false failure under a bare `node --test`. Run only `frontend/tests/*.test.mjs`.

## Stress test numbers

Full detail: [qa/stress/RESULTS.md](../qa/stress/RESULTS.md) (merged 740dd83 and 48d6182). One uvicorn on 127.0.0.1:8110, AI off.

| What | Value |
|---|---|
| Requests | 18,944 in 197 s, 20 concurrent; 0 hangs, 0 crashes |
| Quick routes | p50 11-83 ms, p95 25-250 ms, max 0.6 s, 200-340 req/s |
| Take upload | p50 173 ms, p95 246 ms |
| Live calibration | p50 7.1 s, p95 13.7 s, max 14.3 s (CPU-bound librosa) |
| Camera check | p50 364 ms, p95 397 ms |
| Uploads | 200 MB accepted; 201 MB gets 413 |
| Server memory (RSS) | 165 MB start, 1,321 MB peak, 375 MB end |
| Child processes | peak 3.95 GB total (ffmpeg + homr) |
| Leak check | no growth measured over 6,000 sessions (RSS alone is a weak signal on macOS) |

Stress issues (backend):

| Severity | Issue | Where |
|---|---|---|
| Medium | Session id of 250+ characters gives 500 instead of 404 (`OSError: File name too long`) | `backend/app/store.py:77` |
| Medium | Calibration clip under 1,024 samples gives 500 (librosa `ParameterError`) | `backend/app/takes/calibrate.py:64`, `calibration_routes.py:37` |
| Medium | No cap on concurrent photo scans; 4 scans used 3.95 GB | `backend/app/score/scan_job.py:41-43` |
| Medium | Race when the homr weights download on first run | `backend/app/score/homr_runner.py:56` |
| Low-medium | An upper-case id creates a second in-memory session copy | `backend/app/store.py:101-106` |
| Low | After a 500, keep-alive drops the next request | `backend/app/errors.py:49` |
| Low | JSON of 100,000 `[` gives 500 `RecursionError` | `backend/app/score/routes.py:72` |
| Low | A multipart field over 1 MB gives a misleading 400 | `backend/app/errors.py:44` |
| Low | 3 JPEG magic bytes alone are accepted | `backend/app/score/photo_routes.py:31` |
| Info | The double-confirm message is wrong | `backend/app/score/routes.py:129` |
| Info | The 413 comes only after the full body is spooled | |
| Info | Registries never shrink | `backend/app/store.py:48-49` |

## Browser check

Full detail: [qa/browser/RESULTS.md](../qa/browser/RESULTS.md) (merged 7e3c440). Headless Chrome with `--mute-audio` and a fake mic/camera, real backend on 127.0.0.1:8120, AI off.

- 20 mock and 14 real screen loads, all OK; rapid navigation is clean (nothing left open).
- Not exercised: clicks (record, upload, playback, camera), so those paths rely only on the unit tests.
- Low: the trace screen with an unknown id shows only a banner (`js/trace.js:71-75`).
- Note: on iOS an `interrupted` AudioContext is not resumed (`js/audio.js`).

## Front-end issues

Contract check (29 front-end calls): only `GET /lan-address` has no backend route. The calibration QR then silently falls back to the page's own address with no warning (`frontend/js/calibrate/address.js:11-20`). The practice, progress, exercise, reps and chat routes now exist upstream, so the older "mocked routes" list is obsolete.

### Fixed (all merged and pushed to origin/main)

| ID | Issue | Commit |
|---|---|---|
| FE-1, FE-2 | Stale screen renders; results tests and `--mute-audio` | 5e6c46e |
| FE-3 | Retry queue | 9f983fa |
| FE-24 | Tone kept ringing: no Stop button, Hold up to 1 h, no stop on hidden/pagehide, stop scheduled on the audio clock that iOS freezes. Now: Stop button, a second tap stops, 10 s auto-stop unless Hold, stop on pagehide/hidden | 70816b1 |
| FE-6, FE-7 | `take.js` leak on leave; late upload hijack | b00af54 |
| FE-4, FE-16 | Calibration Try again dropped the re-recorded clip; a rejected clip is now re-recorded; Retry buttons disabled while busy | e4266ef, 7ac42c7 |
| FE-9 | Malformed hash URIError now falls back to `#/start` | c678f36 |

### Open

| ID | Severity | Issue | Where |
|---|---|---|---|
| FE-5 | Medium | Null count-in after reload | `exercise.js:18` |
| F-5 | Medium | MIME allow-list mismatch: backend rejects what the browser may send; every file is named `recording.webm` | `backend/app/takes/validation.py:13-20`, `frontend/js/take/record.js:77` |
| F-4 | Medium | The 35 s chat timeout vs the session lock gives a 409 on retry | chat client / backend session lock |
| FE-8 | Medium | `?api=` accepts any origin | `config.js:4-5` |
| FE-10 | Medium | Score scan panel can be blank | `score/scan_panel.js:22-27` |
| FE-11 | Medium | Score tabs lack an in-flight guard | score tabs |
| FE-12 | Medium | Chat timeout desync | `chat/panel.js:57-62` |
| FE-13 | Medium | No request timeout or cancel | API client |
| FE-14 | Low | | `index.html:16-18` |
| FE-15 | Low | Calibration mic stays open | calibrate |
| FE-17 | Low | `camera_checker` runs two loops | camera_checker |
| FE-18 | Low | Exercise holds the mic between reps | exercise |
| FE-19 | Low | Wrong warning | `score.js:76` |
| FE-20 | Low | `'no-session'` id | |
| FE-21 | Low | Duplicate DOM helpers | |
| FE-22 | Low | Big files; `mock.js` is shipped | |
| FE-23 | Low | Photo decode race | |
| Low | | Mock drift; `requestFeedback` is never called; violin is still accepted (app is trumpet only) | |
| Low | | Calibration 422 clip detection parses message text; suggest the backend add `details.field` | `calibration_routes.py` |
| Unchecked | | `start.js`, `score.js` and `exercise.js` await before touching root (possible stale-render race, same family as FE-1) | |

Note: the exact causes for FE-14, FE-20 to FE-23 and the F-4 location are not restated here beyond the lead's list; see the commit history and the earlier diagnostics threads.

## Backend issues

Static review, not changed. Design comments could not be posted on the LLDs (no tool available), so they live here.

| ID | Severity | Where | Issue and design comment |
|---|---|---|---|
| BE-1 | High, mostly obsolete | `takes/pipeline.py:94-109` | Only `/lan-address` is still missing. Check whether the rep branch here is dead code |
| BE-2 | High | `store.py:75-83` | A restart strands sessions in `scanning`/`processing`. Resume or reset those states on load |
| BE-3 | High | `agents/run.py:121-128` | A global lock is held across the Bedrock call, so one slow call blocks every agent run. Lock per session, not globally |
| BE-4 | High | `calibration_routes.py:34` | No size cap on the calibration upload (the other upload routes have one) |
| BE-5 | High | `diagnosis/runner.py:78-85` | A rerun overwrites `done`, so feedback then returns 409 |
| BE-6 | Medium | `pipeline.py:41-46`, `media_tools.py:75` | Duration limit can be bypassed |
| BE-7 | Medium | upload routes | Size limits are applied after the body is spooled |
| BE-8 | Medium | `score/routes.py:97-114` | Race between concurrent requests |
| BE-9 | Medium | app-wide | No concurrency cap (see the stress findings) |
| BE-10 | Medium | app-wide | No auth, rate limit or CORS policy while bound to 0.0.0.0 |
| BE-11 | Medium | stores | Non-atomic writes; write to a temp file then rename |
| BE-12 | Low | `store.py` | Case-insensitive id duplicates |
| BE-13 | Low | trace route | `str(exc)` leaked in trace |
| BE-14 | Low | media handling | Content-type is trusted; ffmpeg protocols not restricted |
| BE-15 | Low | score import | music21 zip bomb |
| BE-16 | Low | photo routes | No image pixel bounds |
| BE-17 | Low | `diagnosis/timing.py:169` | Read-modify-write outside the lock |
| BE-18 | Low | feedback | Stale feedback after transposition |
| BE-19 | Low | `store.py:80` | An old `session.json` gives 500 |
| BE-20 | Low | misc | Violin accepted; static serves tests/dev/mock; 405 is reported as `bad_request` |

Plus the stress issues above (ids over 250 characters, short calibration clips, scan cap, homr download race). OK: path traversal is blocked; no secrets in the repo.

## Remaining mocked routes

Only `GET /lan-address` has no backend route (the mock answers it). Everything else the front end calls now exists upstream, so the older mocked-routes list is obsolete. `mock/mock.js` is still shipped in the front-end folder (FE-22).

## Leftovers for the owner

- Kill test processes the engine would not let us stop: 75684 (uvicorn :8110), 80315 (uvicorn :8120), Chrome 43584, 43672, 43762, uvicorn 46365 (:8765) and 46417 (:8791).
- Delete leftover Chrome profile folders: `rm -rf /tmp/results-test-*`. The results test leaves one per run; 33 existed on 2026-10-10 after the last rerun.
- An extra remote branch, `task/TASK-22`, was pushed to GitHub; it may be deleted.
- The live servers on :8000/:8001 still run older code (backend d66b628). Restart them to see the fixes.

### Why did the tone keep playing? (owner question)

- Before 70816b1 nothing stopped the tone (FE-24).
- Nothing in `frontend/` survives a tab close: no service worker, mediaSession, looping `<audio>` or reopen.
- The phone likely had extra tone tabs from repeated QR scans (a guess, not verified).
- A stale headless Chrome (PID 43584) spawned an audio service around 21:43 UTC; which page it was on is unknown.

## Not covered

- Clicks in the browser: record, upload, playback, camera. Real microphone and camera hardware, and real iOS/Android devices.
- AI paths: stress and browser runs had AI off (no AWS/Bedrock), so the Bedrock call, its timeouts and cost were not tested.
- Real photo scans beyond 4 at once; 20 concurrent was not tried on purpose.
- Authentication, CORS and rate limiting (none exist), and any deployment behind a proxy.
- Backend findings are from static review and the listed probes; those without a reproduction were not reproduced.
