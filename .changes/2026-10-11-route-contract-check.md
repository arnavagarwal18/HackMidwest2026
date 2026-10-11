---
urgency: ship-soon
component: backend
audience: people
---
`GET /tone?instrument=...&note=...` now serves the phone tone page, as the front-end contract says; before, only `/tone.html` worked and `/tone` answered 404.

# Route contract check (LLD-7 "Web front end" r3)

Compared every backend route with the LLD-7 contract and with what `frontend/js/api.js` calls. Method: read each route, probed the real app with a test client (no AWS), and compared each answer's key set with the `frontend/mock/*.json` files the front end is built against. Not probed live: take upload with real media (needs ffmpeg, not installed here), the photo scan, and calibration with real clips. For those the check is by code reading only.

Errors: every route answers errors as `{ "error": { "code", "message" } }` (validation 422 `bad_request`, unknown path 404 `not_found`, wrong method 405 `bad_request`, uncaught 500 `server_error`), which is what `http.js` reads. Extra keys sit beside `error` (`calibration_failed` sends `notes`), which `http.js` puts in `err.details`.

| route | mismatch | verdict |
|---|---|---|
| POST /sessions | None. 201 `{session_id, instrument}`; bad instrument 422 `bad_request`. Still accepts `violin` (stale; app is trumpet-only now) | comment |
| GET /sessions/{id} | None. Keys match the mock; unknown id 404 `session_not_found` (resume.js reads that code) | fine |
| GET /builtins?instrument= | None. No instrument lists all; an unknown instrument gives `[]` | fine |
| POST /sessions/{id}/score/photo | None. 202 `{score_status:"scanning"}`; multipart field `file`; 409 `wrong_state` while scanning or confirmed; 413/415 | fine |
| GET /sessions/{id}/score/status | Backend adds `referee` and `score_error_message`; the front end does not need them | fine |
| POST /sessions/{id}/score/file | None. Multipart `file` or JSON `{builtin}` (api.js uses both); 404 `builtin_not_found`, 415, 413, 422 `bad_score_file` | fine |
| POST /sessions/{id}/score/confirm | None. 409 `wrong_state` unless scanned | fine |
| GET /sessions/{id}/score?format=json | Not in the LLD-7 list, but api.js `getScore` calls it and the shape matches | comment |
| GET /reference-notes?instrument= | Without `instrument` it answers 422 (builtins answers all); api.js always sends it | fine |
| POST /sessions/{id}/calibration | None. Multipart `ref_0..2`, `click`, optional `inst_0..2`, `click_at_s`; 422 `calibration_failed` carries `notes` as problems.js expects | fine |
| POST /sessions/{id}/calibration/skip | None. `{profile}` | fine |
| GET /sessions/{id}/calibration | None (`profile` is null before any calibration, but resume.js only asks when `has_calibration` is true) | fine |
| POST /sessions/{id}/takes | None on the fields (api.js sends exactly kind, source, bar_from, bar_to, tempo_bpm, count_in_beats, and downbeat_s only when recorded). 202 `{take_id, status}`. The file picker accepts `audio/*,video/*`, but the backend 415s mp3, m4a and `audio/mp4` | comment |
| GET .../takes/{take}/analysis | None. Keys match the mock (the backend adds `outside_count`); statuses processing, transcribed, diagnosed, done, failed; 404 `take_not_found` | fine |
| GET .../takes/{take}/media | None. Streams the file; 404 `take_not_found` | fine |
| GET .../takes/{take}/tracks | None. 404 `no_tracks` for a mic take, 409 `wrong_state` until form is done, gzip when asked | fine |
| GET .../takes/{take}/feedback | None. Flat feedback plus `plan` (load.js unwraps it); 409 `wrong_state` while not ready, which load.js polls on | fine |
| POST .../takes/{take}/feedback | None. 409 `wrong_state` until the take is checked | fine |
| GET /sessions/{id}/feedback/{fb}/trace | None. `{feedback_id, mode, events}`; 404 `feedback_not_found` / `trace_missing` | fine |
| POST /sessions/{id}/camera-check | api.js never sends the optional `view` field, so the backend always detects the view from the picture while the learner's chosen view (front, left, right) stays in the browser | comment |
| GET .../exercises/{ex} | None. `{exercise, state}`; 404 `exercise_not_found` | fine |
| POST .../exercises/{ex}/reps | None. 202 `{rep_id, tempo_bpm, status}`; 409 `wrong_state` while a rep is processing or the exercise is complete | fine |
| GET .../reps/{rep} | None. RepResult keys match the mock; 404 `rep_not_found` | fine |
| GET /sessions/{id}/progress | None. `{before, after, exercises}` | fine |
| GET /lan-address | None. `{url}` | fine |
| GET /tone?instrument=&note= | Not served: 404. Only `/tone.html` worked; the front end itself links `tone.html` | fixed |
| POST /sessions/{id}/transposition | Not in the LLD-7 list; api.js `setTransposition` calls it and the shape matches the mock | comment |
| GET and POST /sessions/{id}/chat | Not in the LLD-7 list; api.js `getChat`/`sendChat` call them and the shape matches the mock | comment |

Counts (27 rows): fixed 1, comment 6, fine 20.

## Proposed design comments (not fixed; each would change the contract or the front end)

- GET /sessions/{id}/score?format=json, POST /sessions/{id}/transposition, GET and POST /sessions/{id}/chat: used by api.js and implemented, but missing from LLD-7 apiContracts; add them to the contract.
- POST /sessions/{id}/camera-check: api.js `checkCamera` sends only `file`; make it also send `view` (the camera_panel choice: front, left or right) so the backend uses the learner's choice instead of guessing from one frame.
- POST /sessions/{id}/takes: the picker offers `audio/*,video/*` but the backend only takes webm, wav, ogg, mp4 and mov; either narrow `accept` in take.js to those types, or have the backend also accept `audio/mpeg` and `audio/mp4` (ffmpeg reads them).
- POST /sessions: still accepts `violin`; drop it from `store.INSTRUMENTS` and `CreateSession` once the trumpet-only decision is final (LLD example is stale).
