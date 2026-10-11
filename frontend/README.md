# Practice Coach front end

Plain JavaScript ES modules, no build step, no framework, no CDN at runtime. FastAPI serves this folder at `/`
(`backend/app/main.py` mounts it as static files), so the page and the API share one origin.

## Layout

| Path | Job |
| --- | --- |
| `index.html` | The single page: header nav (Play `#/take`, Progress `#/progress` only; other screens are reached in context), red/blue banner strip (`#banner`), screen mount (`#screen`). |
| `css/app.css` | All styles. |
| `js/router.js` | Hash router. Maps `#/start`, `#/score`, `#/calibrate`, `#/take`, `#/results/:take`, `#/exercise/:ex`, `#/progress`, `#/trace/:fb` (and the hidden `#/demo`) to `js/screens/<name>.js` and calls its `render(root, params)`. |
| `js/screens/*.js` | One module per screen, each exporting `render(root, params)`. Today they are placeholders (`placeholder.js` prints the saved response of each call the real screen will make). `chat.js` is the Instructor panel (logic in `js/chat/`: `model.js` checks and limits, `transcript.js` drawing, `panel.js` the panel); `results.js` renders it beside the results. |
| `js/results/*.js` | The results screen's parts (see "Results screen" below). `js/dom.js` has the small DOM helpers they share. |
| `js/api.js` | One named function per back-end route (see the file). Screens call these, never `fetch`. |
| `js/http.js` | Transport behind `api.js`: fetch, JSON, `ApiError`, the server-down Retry flow. |
| `js/mock.js` | Mock mode: route table mapping method + path to `mock/*.json`. |
| `js/state.js` | The one shared `state` object; `session_id` is also kept in localStorage. |
| `js/resume.js` | On load, rebuilds state from `GET /sessions/{id}` and picks the start screen. |
| `js/screens/start.js`, `js/score/session.js` | `#/start` is not a gate: with no session it creates one, picks the last-used built-in piece (`localStorage`, else the first of `GET /builtins`), confirms it and goes to `#/take`. On failure: the message, a primary "Try again" and a "Choose a piece" link (`#/score`). |
| `js/screens/score.js`, `js/score/*` | `#/score` ("Change piece"): tabs Built-in (default; one tap chooses and confirms), File, Photo (both show the scan review and Confirm). Every confirm goes to `#/take`. |
| `js/banner.js` | Banner helpers: `reportError`, `showNotice`, `showUnreachable`, `clearBanner`. |
| `js/config.js` | URL switches: `?mock=1`, `?api=<origin>`. |
| `tone.html`, `js/tone/*.js`, `css/tone.css` | The standalone tone page opened on a phone (see "Calibration screen and tone page"). |
| `js/calibrate/*.js` | The calibration screen's parts. |
| `vendor/` | Third-party code (the QR library), with its license; see `vendor/README.md`. |
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
- Reload: `resume.js` reads the stored session id and `GET`s the session. Not confirmed -> `#/score`, confirmed -> `#/take`, except that a confirmed session stays on a deep link
  (`#/calibrate`, `#/results/...`, ...). In mock mode a deep link with no stored session starts the mock session `sess_mock1`.
  `404 session_not_found` clears localStorage, goes to `#/start` (which opens a new session on its own) and shows "Your earlier session was not found; starting fresh."

## Mock mode

Open `http://127.0.0.1:8000/?mock=1`. No request reaches a real route: `mock.js` maps each method + path to
`mock/<file>.json` after a short simulated delay. Polled routes answer `processing` first, then the final response:

| Route | First answers | Then | Restarted by |
| --- | --- | --- | --- |
| `GET .../score/status` | 2 x `get_score_status_processing` | `get_score_status` | `POST .../score/photo` |
| `GET .../takes/{take}/analysis` | 2 x `get_analysis_processing` | `get_analysis` | `POST .../takes` |
| `GET .../exercises/{ex}/reps/{rep}` | 1 x `get_rep_processing` | `get_rep` | `POST .../exercises/{ex}/reps` |
| `POST .../camera-check` | 3 x `post_camera_check` (not in frame) | `post_camera_check_ok` | never |

Mock mode stores its session id under a separate localStorage key. In mock mode the ids `sess_gone` (answers
`session_not_found`) and `sess_unconfirmed` (answers `score_status: none`) let you try the reload paths. The mock
`GET /sessions/sess_mock1` is a confirmed session.

Shapes that LLD-5 does not pin down are guesses in the mocks (`Claim` objects, `Extra`, and the `{ feedback, plan }`
wrapper of the feedback response); the screen coders should correct them when the back end lands.

## Demo upload (`#/demo`)

For live demos, open `http://127.0.0.1:8000/#/demo` (not in the nav; ordinary users never see it). Choose a sheet-music photo and a
video, press Start, and the app runs the normal flow: a new session, `POST .../score/photo`, the normal scan check where you press
Confirm (the only manual step), the video as the take (kind from the file, the Play screen's defaults for bars, tempo and
count-in), then the normal `#/results/:take` screen, where feedback, plan and chat work as usual. The video upload shows its
progress. If the photo cannot be read (or has no bars, or you press Rescan) a message offers "Read the photo again" or a built-in
score, and the same video goes on automatically. A failed step shows its reason with a Retry button and is logged to the browser console.
Code: `js/screens/demo.js` (screen), `js/demo/` (`flow.js` the sequence, `view.js`, `picks.js`, `progress.js`); the take upload is
shared with Play in `js/take/send.js`, and upload progress comes from `js/xhr.js` through the `onProgress` argument of `http.js`.
Mock mode: `?mock=1&scan=failed` makes every photo read fail, `?mock=1&upload=failed` makes the first take upload answer 500.

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

The key: the back end finds it (`diagnosis/transposition.py`) and the analysis carries `transposition: { semitones, source }`
(source `detected`, `user`, `file` or `default`). The browser does not search keys. The results screen shows it as "Key: -4, detected"
(`keyLabel` in `results/transposition.js`; the detection chip, and the can't-tell screen). The Transposition select posts
`POST /sessions/{id}/transposition` (source `user`); `results/rerun.js` then waits for the analysis to show the new key and for the
rebuilt feedback (a new feedback id) and never posts feedback itself. In mock mode a transposition POST has the same effect (`js/mock_transposition.js`).

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

### Instructor chat panel (`js/screens/chat.js`, `js/chat/*.js`)

`results.js` renders the panel at once (it loads `GET /sessions/{id}/chat`) and calls `chat.setResults({ jumpContext, feedback })`
when the take's results are on screen: the feedback sentences become the opening message and the sentences' bar/time jumps
start to work (turns about another take, or a take with no results to jump in, show plain text). Send is disabled while a reply
is pending ("thinking" shows; the UI gives up after 35 s). Errors (including 409 "Instructor is already replying.") go to the
banner and keep the typed text. A `mode: 'fallback'` turn shows "AI instructor unavailable". Mock mode: `take_fallback` gets
the fallback reply (`mock/post_chat_fallback.json`), other takes the AI reply (`mock/post_chat.json`).
Tests: `node --test frontend/tests/chat.test.mjs` (no browser).

### Video overlay (`js/results/overlay.js`)

For a video take the results screen draws the tracked body over the video and lists the form flags. `screens/results.js` calls
`mountOverlay(renderDone(...), { sessionId, take })` after rendering and destroys the previous overlay when the screen is rendered
again; a mic take returns `null` (no canvas, no tracks fetch).

| File (`js/results/overlay/`) | Job |
| --- | --- |
| `frames.js` | `nearestFrame(frames, t)`: binary search on `t`; `null` when there are no frames or the nearest is more than 0.2 s away. |
| `geometry.js` | `contentRect(box, intrinsic, objectFit)` (where the picture sits in the element, so letterboxing lines up) and `toCanvas`. |
| `flag_points.js` | `RULE_LANDMARKS` (rule -> pose points; `trumpet_head_down`, `trumpet_elbows_pinned`, `trumpet_elbows_wide`, `trumpet_bell_angle`, `shoulders_raised`, `slouching`), `involvedLandmarks(flag)` (respects `side`), `activeFlags`. |
| `draw.js` | Pose lines (shoulders, elbows, wrists, ears to shoulders, shoulders to hips), hand points, red points and the label during a flag. |
| `flag_list.js` | The list in `#form-flag-slot`; each row jumps with `jumpTo(resolveId(flag.id, index))` to `peak_s`. |

`GET .../tracks` is fetched once, when `form_status` is `done` (`onAnalysis(analysis)` does nothing after the first fetch). A failure
(4xx, 5xx, unreachable, or an answer with no `frames`) is logged, hides the overlay and shows "Body lines unavailable" next to the
checkbox slot; the flag list and the rest of the screen keep working and nothing retries. The "Show body lines" checkbox stops the
animation-frame loop and clears the canvas. The loop and the `hashchange` listener stop on leaving the route (and the loop also stops
by itself if the screen was replaced). In mock mode `mock/get_tracks.json` covers the 12 s mock video, with a flagged second at 6 to 7 s.

Tests: `node --test frontend/tests/overlay.test.mjs` (fake canvas and DOM; no browser).

## Take setup (`#/take`)

`js/screens/take.js` joins the pieces in `js/take/`:

| File | Job |
| --- | --- |
| `setup.js` | Defaults (bars 1..N, score tempo, one bar of count-in; a saved `state.take_setup` wins field by field), `validateSetup`, `takeFields` (the POST `/takes` text fields; no `downbeat_s` for an uploaded file). |
| `take_form.js` | The form: tempo (30-240) with a - / + stepper (steps of 2) and the "Add camera" toggle up front; bar from/to, count-in (0-8) and the metronome (with the headphones note) under "More options". |
| `../play/prefs.js` | Remembers the tempo (per session, i.e. per piece) and the camera on/off in localStorage (`practice_coach_play_prefs`). |
| `camera_panel.js` | Live preview + guide outline + badge; owns the checker. `attach(stream)` / `pauseChecks()` / `detach()`. |
| `camera_checker.js` | One `camera-check` about every second (never overlapping), stops on `stop()` or on the first failure. |
| `camera_status.js` | Answer -> badge text (`In frame`, `Move back: right elbow not in view`, too small, too dark). |
| `camera_guide.js` | The SVG outline over the camera preview (head, shoulders, arms and the trumpet). `CAMERA_POSITION = 'front'`: the front-vs-45-degrees question is settled by editing this one file. |
| `frame_capture.js` | One 640 px wide JPEG from the `<video>`. |

Flow: Record -> `recordTake` with the setup -> Stop (or the 180 s cap, with a notice) -> `POST /takes` -> save `state.current_take_id` and
`state.take_setup` -> `#/results/{take_id}`. A refused upload (for example 422 `bad_request`) shows the server's message in the red banner,
keeps the inputs and the recording, and offers "Send this take again" (the inputs can be corrected first). A server that is down shows the
Retry banner, which keeps the recording. A blocked mic or camera shows `renderMediaError` with an upload option. Camera checks stop while
recording and on leaving the screen; a failed check (for example 503 `form_unavailable`) hides the badge and leaves a small note, and recording
stays allowed.

After a reload `state.score.bars` is unknown, so the screen reads `GET /sessions/{id}/score?format=json` (`api.getScore`).
Tests: `node --test frontend/tests/take.test.mjs` (logic only; no browser).

## Calibration screen and tone page

`#/calibrate` (`js/screens/calibrate.js`, parts in `js/calibrate/`) needs a session. Flow: it reads `GET /reference-notes?instrument=`,
shows the QR code and address of the tone page, then three rows ("Play Bb3 on your other device now", 3 s each, with a level meter),
the delay test (a click through the laptop speaker 0.5 s after the 2 s recording starts; `click_at_s` comes from `recordClip`),
and three optional rows for the same notes on the instrument. **Send calibration** posts `ref_0..2`, `click`, `click_at_s` (and `inst_0..2`)
with `api.submitCalibration`. A 422 `calibration_failed` (`err.details.notes = [{ asked, problem, cents }]`, problems `not_heard`,
`off_pitch`, `too_noisy`) shows the red banner plus a list "F4: not heard [Retry]"; Retry records just that note again, and Send is
enabled once every failed note has a new clip. Other errors show `err.message` and keep the clips in memory. **Skip calibration** calls
`.../calibration/skip`, stores the default profile in `state.calibration` and goes to `#/take`. A blocked mic shows `renderMediaError`.
The mic and timers are released when the route changes.

The notes and Hz and "Or use any tuner app or keyboard that plays these notes." are always on screen, so calibration works when the phone
cannot open the tone page (Wi-Fi isolation, firewall).

**Address:** the back end has no `GET /lan-address` route yet (it is mocked: `mock/get_lan_address.json`). When the real call fails,
`calibrate/address.js` falls back to this page's own address; if that is localhost the screen says the phone needs the laptop's
Wi-Fi address instead. The tone page is the static file `frontend/tone.html`, so its URL is `<address>/tone.html?instrument=trumpet`
(`StaticFiles` mount at `/`; `?note=F4` marks one note; without `instrument` the page uses trumpet as the one being asked for).

**Tone page** (`tone.html`, `js/tone/page.js`, `player.js`, `lifecycle.js`): standalone, no app shell. One button per note ("F4 - 349.23 Hz"), the first tap
creates the AudioContext, a sine at the exact Hz plays at gain 0.5 with 20 ms gain ramps. The playing button is highlighted.
Tapping another note stops the current one first; tapping the playing note stops it. A big **Stop** button stays on screen: it sets gain to 0,
stops the source and suspends the AudioContext. The tone stops by itself after 10 s (a wall-clock timer, not the audio clock) unless **Hold** is on;
Hold keeps it until Stop or a tap on the note (turning Hold off starts a fresh 10 s). `pagehide` and the page turning hidden (phone locked, app switched) also stop it.

**QR library:** `vendor/qrcode.js` (qrcode-generator, MIT) is loaded by `index.html`; `calibrate/qr.js` draws it as an SVG built from DOM nodes.

Mock variants: `?mock=1` answers calibration successfully; `?mock=1&calibration=failed` answers the first POST with a 422
`calibration_failed` (F4 not heard, Bb4 off pitch) and succeeds afterwards. Try the tone page at `/tone.html?mock=1`.

Tests: `node --test frontend/tests/calibrate.test.mjs frontend/tests/tone.test.mjs` (logic only, with the fake browser in `tests/fake_env.mjs`; no browser).

## Loop trainer (`#/exercise/:ex`)

`js/screens/exercise.js` wires `js/exercise/trainer.js` to the real API and recorder; the trainer takes them as `deps`, so node
tests can drive it. `exercise/model.js` is pure wording and ladder logic, `exercise/view.js` rebuilds the screen from one model
object (phases: `loading`, `ready`, `recording`, `sending`, `scoring`, `result`, `not_counted`, `send_failed`, `too_long`,
`check_failed`, `media_error`, `upload`, `complete`, `load_failed`).

- Flow: GET the exercise and state (again before every rep, because the back end owns the tempo) -> Record rep (the button or
  space) runs the count-in at `current_bpm` through `recordTake` (cap 60 s) -> space or Stop -> `POST .../reps` -> poll
  `GET .../reps/{rep}` every 1 s -> PASS / FAIL with the reasons, the tempo change and `Next rep at N BPM - press space`.
  When `exercise_complete` it shows Done and `Record a full take` (to `#/take`, filling the bars only if none were chosen).
- The mic opens once and is reused. An exercise with a `form_rule` asks for the camera; if only the camera fails it records
  the sound only (kind `mic`) and shows a notice. Mic trouble shows `renderMediaError` with an Upload option.
- Errors never retry by themselves: a refused upload keeps the recording for `Send again`; `not_counted` / `failed` reps show the
  back end's reasons and `Record again`; polling follows the results screen (`?poll_ms=`, `?slow_after_s=`, `?give_up_after_s=`).
  Leaving the route stops the recording, the mic and the space listener.
- Mock mode: the exercise id picks the variant. `ex1` passes (streak 2 of 3), `ex_fail` fails, `ex_not_counted` does not count,
  `ex_complete` is one pass from the target and its rep completes it, `ex_done` is already complete, `ex_video` has a form rule.
  The mock answers with fixed files, so it does not step the tempo itself; `tests/exercise_trainer.test.mjs` does that against a
  fake back end that applies the LLD-6 rules.

Tests (no browser): `node --test frontend/tests/exercise_model.test.mjs frontend/tests/exercise_trainer.test.mjs frontend/tests/exercise_mock.test.mjs`
(`tests/fake_dom.mjs` is the small DOM stand-in they share). Not covered: real microphone/camera recording and the screen's look.
