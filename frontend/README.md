# Practice Coach front end

Plain JavaScript ES modules, no build step, no framework, no CDN at runtime. FastAPI serves this folder at `/`
(`backend/app/main.py` mounts it as static files), so the page and the API share one origin.

## Layout

| Path | Job |
| --- | --- |
| `index.html` | The single page: header nav, red/blue banner strip (`#banner`), screen mount (`#screen`). |
| `css/app.css` | All styles. |
| `js/router.js` | Hash router. Maps `#/start`, `#/score`, `#/calibrate`, `#/take`, `#/results/:take`, `#/exercise/:ex`, `#/progress`, `#/trace/:fb` to `js/screens/<name>.js` and calls its `render(root, params)`. |
| `js/screens/*.js` | One module per screen, each exporting `render(root, params)`. Today they are placeholders (`placeholder.js` prints the saved response of each call the real screen will make). `chat.js` is the Instructor panel; `results.js` renders it beside the results. |
| `js/results/*.js` | The results screen's parts (see "Results screen" below). `js/dom.js` has the small DOM helpers they share. |
| `js/api.js` | One named function per back-end route (see the file). Screens call these, never `fetch`. |
| `js/http.js` | Transport behind `api.js`: fetch, JSON, `ApiError`, the server-down Retry flow. |
| `js/mock.js` | Mock mode: route table mapping method + path to `mock/*.json`. |
| `js/state.js` | The one shared `state` object; `session_id` is also kept in localStorage. |
| `js/resume.js` | On load, rebuilds state from `GET /sessions/{id}` and picks the start screen. |
| `js/banner.js` | Banner helpers: `reportError`, `showNotice`, `showUnreachable`, `clearBanner`. |
| `js/config.js` | URL switches: `?mock=1`, `?api=<origin>`. |
| `mock/*.json` | One saved response per route (plus `*_processing.json` for polled routes), `take_media.wav`. |

## Adding or filling in a screen

1. Edit `js/screens/<name>.js`; keep `export function render(root, params)` (may be async).
2. Call `api.js` functions with `state.session_id`. Let errors propagate: the router shows `err.message` in the red banner.
   If you catch one yourself (to keep a form on screen), call `reportError(err)` and leave the inputs alone.
3. Never retry automatically. A server-down error already shows "Can't reach the app server on this laptop" with a Retry
   button that repeats the request once per press; the call resolves when it succeeds.
4. Keep inputs and any recorded `Blob` in module variables or `state`, not in the DOM, so a banner never loses them.

## Errors

- HTTP 4xx/5xx with `{ error: { code, message } }` -> `api.js` throws `ApiError` (`code`, `message`, `status`, `details`).
  `details` holds every other key of the body (for example `notes` on a 422 `calibration_failed`).
- Fetch rejects (server not running) -> the banner above; inputs stay in memory.
- Reload: `resume.js` reads the stored session id and `GET`s the session. Not confirmed -> `#/score`, confirmed -> `#/take`.
  `404 session_not_found` clears localStorage, goes to `#/start` and shows "Your earlier session was not found; starting fresh."

## Mock mode

Open `http://127.0.0.1:8000/?mock=1`. No request reaches a real route: `mock.js` maps each method + path to
`mock/<file>.json` after a short simulated delay. Polled routes answer `processing` first, then the final response:

| Route | First answers | Then | Restarted by |
| --- | --- | --- | --- |
| `GET .../score/status` | 2 x `get_score_status_processing` | `get_score_status` | `POST .../score/photo` |
| `GET .../takes/{take}/analysis` | 2 x `get_analysis_processing` | `get_analysis` | `POST .../takes` |
| `GET .../exercises/{ex}/reps/{rep}` | 1 x `get_rep_processing` | `get_rep` | `POST .../exercises/{ex}/reps` |

Mock mode stores its session id under a separate localStorage key. In mock mode the ids `sess_gone` (answers
`session_not_found`) and `sess_unconfirmed` (answers `score_status: none`) let you try the reload paths. The mock
`GET /sessions/sess_mock1` is a confirmed session.

Shapes that LLD-5 does not pin down are guesses in the mocks (`Claim` objects, `Extra`, and the `{ feedback, plan }`
wrapper of the feedback response); the screen coders should correct them when the back end lands.

## Recording and metronome

For the take setup, loop trainer and calibration screens. Import from `js/record.js` (it re-exports the error helpers and
`getAudioContext`) and `js/metronome.js`. All timing uses the one shared `AudioContext` (`js/audio.js`), never `setTimeout`.
Start recording from a click handler: browsers only let the audio context run after a user gesture.

```js
import { openStream, recordTake, recordClip, renderLevelMeter, renderMediaError, stopStream } from '../record.js';

try {
  const { stream, hasVideo, cameraError } = await openStream({ video: true }); // cameraError: mic-only fallback, show as a notice
  const take = await recordTake({ stream, tempoBpm: 80, countInBeats: 4, metronomeOn: false, maxSeconds: 180,
    onAutoStop: (result, err) => { /* the cap was reached: result.message, or err if stopping failed */ } });
  const result = await take.stop();   // { blob, file, mimeType, downbeat_s, duration_s, autoStopped, message }
  await api.uploadTake(state.session_id, result.file, { kind, source: 'recorded', bar_from, bar_to,
    tempo_bpm: 80, count_in_beats: 4, downbeat_s: result.downbeat_s });
} catch (err) {
  if (err.name === 'MediaAccessError') renderMediaError(root, err, { onTryAgain: start, onUpload: showFilePicker });
  else throw err;
}
```

| Function | What it does |
| --- | --- |
| `openStream({ video })` | Opens the mic (and camera). Throws `MediaAccessError { device: 'mic' or 'camera', reason: 'blocked' / 'missing' / 'busy' / 'unknown', message }`. If only the camera fails it resolves mic-only with `cameraError`. Never retries. |
| `renderMediaError(container, error, { onTryAgain, onUpload })` | Fills `container` with the message, the help line (`Allow it in Chrome: click the camera icon in the address bar`, for blocked), a Try again button and (if `onUpload` is given) an Upload button. |
| `recordTake({ stream, tempoBpm, countInBeats = 4, metronomeOn = false, beatsPerBar = 4, maxSeconds = 180, onAutoStop })` | Starts recording and the count-in clicks (first click 0.5 s after the start, then every 60 / tempo s, accent on beat 1). With `metronomeOn` the clicks continue until stop. Resolves a handle `{ recStart, stop() }`. Use `maxSeconds: 60` for reps. |
| `take.stop()` | Promise of `{ blob, file, mimeType, downbeat_s, duration_s, autoStopped, message }`. `downbeat_s = 0.5 + countInBeats * 60 / tempoBpm`. `file` is a named `File` for `api.js`; keep `result` in memory so a failed upload can be retried with the same file. |
| `recordClip({ stream, durationS, clickAfterS = null })` | Fixed-length clip (calibration: 3 s per note; 2 s with `clickAfterS: 0.5`). Resolves `{ blob, file, mimeType, click_at_s }`; `click_at_s` is the scheduled click time minus the recording start (null with no click). The click plays through the speaker for the mic to hear. |
| `createLevelMeter(stream, onLevel)` / `renderLevelMeter(container, stream)` | Input level 0..1 once per animation frame / a ready `<meter>`. Both return `{ stop() }`. |
| `stopStream(stream)` | Releases the mic and camera. |
| `metronome.js`: `startMetronome({ audioCtx, tempoBpm, startTime, beatsPerBar, maxBeats })`, `scheduleClick(audioCtx, time, accent)` | The click scheduler (100 ms look-ahead). `startMetronome` returns `{ stop() }`; the loop trainer can use it directly. |

Time zero of a recording is the AudioContext time just before `MediaRecorder.start()`, not the `start` event: in Chrome the
event arrives about 60 ms after capture begins, which shifted every click by that much in the recorded file.

Try it: open `/dev/record-test.html` (developers only; `?auto=loopback`, `?auto=clip`, `?auto=blocked`).

## Results screen (`#/results/:take`)

`js/screens/results.js` polls the analysis (`results/polling.js`: every 1 s, 'Still working' after 90 s, stops at 300 s with
Check again / Record again; shorten for tests with `?poll_ms=100&slow_after_s=1&give_up_after_s=3`), then `results/view.js`
renders the finished take. `results/load.js` is the only place that knows the shape of `GET .../feedback` (the back end
sends `{...feedback, plan}`; an older mock wrapped it as `{feedback, plan}`; both are accepted).

For the overlay and chat coders:

- **Video container:** `#results-media` > `.video-stage` (position: relative) > `<video>`; put the overlay canvas in `.video-stage`.
  Beside it is an empty `#form-flag-slot` for the form flag list. `view.js`'s `renderDone` returns `{ index, jumper, player, barList, ... }`.
- **Jumping:** `jumper.jumpTo(place)` moves the media and highlights the bar row. Form flags: `jumpTo(resolveId(flag.id, index))`
  seeks to `peak_s` exactly (sentences start 1 s early).
- **Reusable rendering** (`results/sentences.js`): `renderSentence`, `renderSentenceList`, `renderChip`; they take a jump context
  `{ index, jumper }` where `index = buildMeasurementIndex(analysis)` (`results/measurements.js`) and `jumper = createJumper({ player, barList })`.
- The analysis has no `kind`; a take counts as video when `state.take_setup.kind === 'video'` or `form_status !== 'none'`.

Mock takes for trying each state (use them as the take id): `take_1` (video), `take_mic`, `take_fallback`, `take_failed`,
`take_cant_tell`, `take_stuck` (never finishes). Mock mode records each request in `mockRequestLog` (`js/mock.js`).

Tests: `node frontend/tests/results.test.mjs` (Node 22+, Chrome). It runs one small headless Chrome (low-memory flags) and
stops it when done.
