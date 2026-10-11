# Browser check of every screen (2026-10-10)

Headless Chrome (one instance, `--mute-audio`, fake microphone/camera), the app served by the real back end on 127.0.0.1:8120 with AI off (no AWS/Bedrock settings).
Run: `node qa/browser/run.mjs` (needs the back end running; see `run.mjs`). It writes `qa/browser/results.json` (gitignored) with the full per-screen record.
Nothing was clicked: every screen was only loaded and left for 2.5 s. Recording, playback and the Retry buttons were not exercised.

## Result: 34 screen loads, 34 OK, 0 with errors

Per load the script records console errors and warnings, uncaught exceptions, failed requests (URL + status), the main heading, the text in the screen,
the red banner, and a blank-screen check. "OK*" means the only failures were requests/console errors that the situation is meant to produce
(listed in `routes.mjs`, field `expected`); they are described under "Expected failures" below.

| Screen | Mock (`?mock=1`) | Real back end |
|---|---|---|
| #/start | OK | OK |
| #/score (session not confirmed) | OK | OK |
| #/calibrate | OK | OK* (GET /lan-address 404) |
| #/take | OK | OK |
| #/results/:take, analysed take | OK (take_1, take_mic, take_cant_tell, take_fallback, take_stuck) | OK (t2, "I couldn't tell") |
| #/results/:take, failed take | OK (take_failed) | OK (t1, "This take could not be checked") |
| #/results/take_missing | n/a | OK* (404, banner "We couldn't find that take.") |
| #/exercise/:ex | OK (ex_1, ex_fail, ex_not_counted, ex_complete, ex_done, ex_video) | OK (ex1) |
| #/exercise/ex_missing | n/a | OK* (404, in-page message + banner) |
| #/progress | OK | OK |
| #/trace/:fb | OK (fb_1) | OK (fb2) |
| #/trace/fb_missing | n/a | OK* (404, banner only) |
| tone.html?instrument=trumpet | OK | OK |
| #/start with a stored session id the server does not know | OK (banner "Your earlier session was not found; starting fresh.") | OK* (GET /sessions/no_such_session 404, same banner) |

No uncaught exceptions, no console warnings, no blank screen, no redirect away from the requested hash, and no request cancelled by the app in any load.
The real-mode data was built through the API: session, built-in trumpet score, confirm, calibration skip, one synthetic take that transcribes
(`synth_take.mjs`), one silent take that fails (`no_notes_heard`), and its fallback feedback and plan (AI off, so `mode: fallback`).

## Rapid navigation

Eight routes x 3 cycles at 120 ms per step in one page load, then 2.5 s of waiting, then a move to #/start and another 2.5 s.
Counted by a script injected before the app: open `setInterval`s, pending `setTimeout`s, live microphone tracks, open `AudioContext`s, playing media.

| Mode | Console errors | Exceptions | Failed requests | After cycles | After leaving to #/start |
|---|---|---|---|---|---|
| mock | 0 | 0 | 0 | all 0 | all 0 |
| real | 3 (all GET /lan-address, once per visit to #/calibrate) | 0 | 3 (same 404s) | all 0 | all 0 |

No leftover timers, streams or audio contexts. (The take screen left no live microphone track just by being loaded.)

## Expected failures and how the UI handles them

- **GET /lan-address has no back-end route** (confirmed: 404 from the real server). #/calibrate handles it: it logs `console.error` and falls back to the page's own address
  (`frontend/js/calibrate/address.js:19`), and still renders. The fallback address is `127.0.0.1:8120` here, which a phone cannot reach, so the QR code is only useful when the page was opened by the computer's LAN address.
- **Exercise, progress and rep routes DO exist in the back end now** (the brief said they did not): `backend/app/practice/routes.py` and `rep_routes.py`.
  GET /sessions/{id}/progress answered 200 and GET /sessions/{id}/exercises/ex1 answered 200 with real data. POST .../reps and GET .../reps/{rep} were not called (they need a recording).
- **Unknown take, exercise or feedback ids** answer 404 and the UI shows the server's message in the red banner (clean error states, not broken). Each also logs one
  `console.error('Request failed:', ...)` from `frontend/js/banner.js:56` by design.

## Issues found

| # | Severity | Issue | Where |
|---|---|---|---|
| 1 | Low | #/trace/<unknown id> shows only the red banner; the screen area stays completely empty (no heading, no "not found" text, no link back). #/results/<unknown take> keeps its "Results" heading and the exercise screen shows an in-page message, so the trace screen is the odd one out. | `frontend/js/screens/trace.js:71-75` (`render` has no catch, so the router's `reportError` is the only output, `frontend/js/router.js:56`) |
| 2 | Low | Without GET /lan-address the calibration QR code points at whatever address the page was opened with; on `127.0.0.1` or `localhost` the phone link cannot work, and the screen gives no warning beyond the console. | `frontend/js/calibrate/address.js:11-20`; no back-end route for it (`backend/app/main.py` includes none) |
| 3 | Info | The brief's list of missing routes is out of date (see above); the mock still has files for them (`frontend/mock/get_exercise.json`, `get_progress.json`) that match the real routes' shape well enough for the screens to render. | `backend/app/practice/routes.py` |
| 4 | Info | A results screen for a take that is still processing keeps one `setTimeout` pending (the poll wait), as designed; it is gone after leaving the screen. | `frontend/js/results/polling.js:18,34` |

Not covered: anything that needs a click or a recording (Record, Retry, upload buttons, playback), the rep POST, camera check, and a real AI run.

## Notes on the harness

- Chrome is started through `chrome_fake_media.sh` (set as `CHROME`), which adds the fake-media flags and then `exec`s the real Chrome, so `frontend/tests/browser.mjs` is reused unchanged and still adds `--mute-audio`.
- `page_probe.mjs` opens a second DevTools connection to the same tab for warnings, network failures and the open-resource counts; `/favicon.ico` requests (asked for by the bare CSS page used to reach localStorage) are ignored.
- `run.mjs` stops Chrome on normal end, SIGINT and uncaught errors. If a run is killed from outside, a leftover Chrome can be closed with the DevTools `Browser.close` command on its port (see `DevToolsActivePort` in its `/tmp/results-test-*` profile).
