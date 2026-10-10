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
