# Backend stress test: results

Run on 2026-10-10, macOS laptop, one uvicorn process (`app.main:app`, `--app-dir backend`) on **127.0.0.1:8110** only, never 8000/8001. AI off (`AI_ENABLED=false`, no AWS/Bedrock credentials). Session data in the worktree's own `data/sessions` (deleted at the end of the run). Full run: 18,944 requests in 197 s, at most 20 in flight, nothing over 30 s, server never crashed.

Reproduce: start `AI_ENABLED=false backend/.venv/bin/python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8110`, then from `qa/stress/` run `../../backend/.venv/bin/python run_stress.py --pid <uvicorn pid>` and `python report.py`. This top part (`findings.md`) is hand-written; everything under "Tables" is generated from `out/results.json`.

## Headline numbers

| what | value |
|---|---|
| Requests / wall time | 18,944 in 197 s, 20 concurrent clients |
| Hangs (>30 s) | 0 |
| Server crashes | 0 |
| Cheap routes (sessions, builtins, score, chat, status) at 20 concurrent | p50 11-83 ms, p95 25-250 ms, max 0.6 s; 200-340 req/s |
| Take upload (2 s wav/webm) | p50 173 ms, p95 246 ms; the background pipeline finished all 160 takes |
| Live calibration (3 reference clips + click) | **p50 7.1 s, p95 13.7 s, max 14.3 s**; about 2 per second in total (CPU-bound librosa work) |
| Camera check | p50 364 ms, p95 397 ms |
| Real photo scan (homr; 1 alone, then 3 at once) | each ended `scanned` in 3-12 s (weights already downloaded) |
| Large uploads (streamed) | take 10/50/200 MB accepted (202); 201 MB gets 413; score file over 5 MB, photo over 15 MB, camera frame over its limit get 413 |
| Server RSS (uvicorn PID) | start 165 MB, **peak 1,321 MB** (while the 10/50/200 MB takes were processed), end 375 MB |
| Child processes (ffmpeg, homr) | **peak total 3.95 GB** RSS across the run (summed over direct children, sampled every 2 s) |
| Leak check (4 rounds x 1,500 new sessions) | RSS 568, 569, 372, 373, 375 MB: no growth we could measure (macOS compresses idle memory, so RSS alone is a weak signal) |

## Issues, worst first

| # | severity | route / input | what happens | repro (one line) | where in the code |
|---|---|---|---|---|---|
| 1 | medium | any `/sessions/{id}/...` with an id of about 250+ characters | **500** instead of 404 (`OSError: File name too long`) | `curl -i 127.0.0.1:8110/sessions/$(python3 -c "print('a'*300)")` | `backend/app/store.py:77` `path.is_file()` raises; `get()` (line 102) only guards with `isalnum()`, not length |
| 2 | medium | `POST /sessions/{id}/calibration` with a clip of fewer than 1,024 samples (e.g. a truncated wav) | **500** (`librosa ParameterError: Input is too short (n=478) for frame_length=1024`) | send `ref_0` = the first 1,000 bytes of a valid wav (case "truncated ref_0 wav" in `scenarios_malformed.py`) | `backend/app/takes/calibrate.py:64` `_rms_db`; `calibration_routes.py:37` only catches `MediaError` and `OSError` |
| 3 | medium | photo scans: no cap on concurrent scans | each scan starts its own thread plus homr subprocess; summed child RSS peaked at **3.95 GB** with only about 4 scans (+ ffmpeg) at once. 20 concurrent real photos would likely exhaust a laptop (not tried on purpose) | upload 4+ real photos to `/sessions/{id}/score/photo` at the same time | `backend/app/score/scan_job.py:41-43`, no semaphore |
| 4 | medium | first photo scan after install | homr downloads its model weights (about 25+47+53 MB) on first use. Three first scans at once raced on the same file: two failed with `scan_failed` (`FileNotFoundError ... segnet_...zip`). Seen in the first, aborted run (server log, not kept); later runs had the weights and passed. A first scan also needs network | fresh venv, then 3 concurrent real photo uploads | `homr/main.py:347` (third-party), started from `backend/app/score/homr_runner.py:56` |
| 5 | low-medium | macOS (case-insensitive disk): `/sessions/<ID in UPPERCASE>` | returns the session, but the store keeps a **second in-memory copy** under the upper-case key (own lock). A write through one spelling is invisible through the other until restart: skip calibration via UPPER, then `GET calibration` via lower still says `profile: null` | `curl -XPOST 127.0.0.1:8110/sessions/<UPPERCASE id>/calibration/skip`, then `GET .../calibration` with the lower-case id | `backend/app/store.py:101-106` cache keyed by the raw id; `_load` finds the file through the case-insensitive filesystem |
| 6 | low | any unhandled 500 | uvicorn closes the keep-alive connection after it: the **next request on that connection fails with ReadError/disconnect** (6 of 6 throwaway follow-ups failed; also reproduced by hand 3 of 3). Browsers usually retry, scripts may not | POST 100,000 `[` as JSON to `/score/file`, then any GET on the same connection | `backend/app/errors.py:49` the catch-all handler returns 500 and Starlette then re-raises ("Exception in ASGI application" in the log) |
| 7 | low | `POST /sessions/{id}/score/file`, JSON body of `[` repeated 100,000 times | **500** (`RecursionError` while decoding JSON) | `python3 -c "print('['*100000)" \| curl -i -XPOST -H 'content-type: application/json' --data-binary @- 127.0.0.1:8110/sessions/<id>/score/file` | `backend/app/score/routes.py:72` catches `ValueError` only (RecursionError is a `RuntimeError`). The same body to `POST /sessions` returns a clean 400 |
| 8 | low | a multipart text field over 1 MB (e.g. `tempo_bpm`) | 400 with the misleading message "Check the address and try again" | post `tempo_bpm` = 5 MB of `x` to `/sessions/{id}/takes` | Starlette's field-size limit is turned into a generic 400 by `backend/app/errors.py:44` |
| 9 | low | `POST /sessions/{id}/score/photo` with only the 3 magic bytes `ff d8 ff` | accepted (202); a scan starts and then fails in the background (`scan_failed`) | upload `b"\xff\xd8\xff"` as `p.jpg` | `backend/app/score/photo_routes.py:31` checks the signature only |
| 10 | info | double confirm | 409 as expected, but the message says "There's no scanned score to confirm yet" when the score is already confirmed | `POST .../score/confirm` twice | `backend/app/score/routes.py:129` |
| 11 | info | oversized uploads | rejected with 413 only after the whole body has been received and spooled (200 MB takes 150-190 ms on localhost; longer on a real network) | 200 MB `.musicxml` to `/score/file` | Starlette parses the multipart form before the handler's size check |
| 12 | info | in-memory registries never shrink | `_sessions` and `_locks` (`store.py:48-49`) plus the chat and pipeline lock dicts grow with every session id for the life of the process. No RSS growth measured over 6,000 sessions, so the per-session cost is small | n/a | `backend/app/store.py:48-49` |

## What held up

- Concurrent writers on **one** session (20 at once): 20 builtin picks all 200; confirm 1x200 + 19x409; 20 take uploads got 20 unique ids (t1-t20) and all 20 finished `done`; API and `session.json` agreed (20 takes each); chat 9x200 + 11x409 ("already replying") with 18 turns stored (= 9 replies x 2); 20 transposition changes all 200.
- Every route returns 404 `session_not_found` for an unknown id; odd ids (unicode, `..%2F..`, `%00`, spaces) never escaped the sessions folder.
- Path-traversal filenames (`../../evil.wav`) are ignored (files are stored under generated names).
- Out-of-order calls (take before confirm, transposition before confirm, score before upload, photo after confirm, rerun feedback while processing) all return 409 `wrong_state`.
- Bad numbers (nan, inf, 1e999, 10**30, negative, non-ASCII digits), bad JSON, wrong types, zero-byte files, wrong content types: clean 4xx with the standard error body.
- The nested XML entity-expansion file was rejected with 422.
- AI off: chat returns 200 with `mode: fallback, fallback_reason: disabled`; feedback rerun returns 200 (fallback); no AWS calls were made.
- Malformed takes (truncated webm/wav, zero-byte wav, wav bytes labelled mp4) are accepted with 202 and fail later in the background pipeline, not at upload; their final status was not checked individually.

## Caveats

- Not tested on purpose: 20 concurrent real photo scans (memory risk, issue 3), a decompression-bomb image for the camera check (could allocate GBs), browser and audio paths, `tracks` for a real video take (every audio take correctly returns 404 `no_tracks`).
- The photo probes share one session, so the "no file field" probe got 409 (the session was already scanning from the previous probe), not the 422 it would otherwise return.
- The engine refused this agent's `kill` of the server it started (see the report for the PID). The RSS "start" is the process after earlier smoke runs, not a cold boot (cold boot after imports was about 150 MB).
- `disk_after_*` numbers in the tables include about 970 MB of leftovers from two earlier aborted runs of this script; the large-upload phase itself added about 274 MB. Session folders were deleted at the end of the run.


## Tables


## Per-route load and large-input numbers


### 1 sessions create/get (wall 3.76 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions` | 800 | 18.3 | 171.8 | 531.0 | 201×800 | 213.0 |
| `GET /sessions/{id}` | 800 | 16.5 | 163.3 | 613.7 | 200×800 | 213.0 |

### 2 builtins/reference notes (wall 3.11 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `GET /builtins` | 800 | 14.9 | 133.7 | 477.2 | 200×800 | 256.8 |
| `GET /reference-notes` | 800 | 14.0 | 132.4 | 468.1 | 200×800 | 256.8 |

### 3 score upload/confirm/read (wall 4.02 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions` | 400 | 32.6 | 89.3 | 235.7 | 201×400 | 99.6 |
| `POST /sessions/{id}/score/file (musicxml upload)` | 200 | 83.2 | 250.0 | 267.7 | 200×200 | 49.8 |
| `GET /sessions/{id}/score?format=musicxml` | 200 | 16.7 | 36.8 | 183.8 | 200×200 | 49.8 |
| `GET /sessions/{id}/score?format=json` | 200 | 21.9 | 113.5 | 193.7 | 200×200 | 49.8 |
| `GET /sessions/{id}/score/status` | 200 | 43.5 | 124.7 | 197.8 | 200×200 | 49.8 |
| `POST /sessions/{id}/score/confirm` | 200 | 37.2 | 123.6 | 241.9 | 200×200 | 49.8 |
| `POST /sessions/{id}/score/file (builtin)` | 200 | 54.9 | 119.5 | 224.8 | 200×200 | 49.8 |

### 4 prepare 20 confirmed sessions (wall 0.14 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions` | 20 | 58.9 | 96.4 | 129.2 | 201×20 | 138.8 |
| `POST /sessions/{id}/score/file (builtin)` | 20 | 24.0 | 62.8 | 66.3 | 200×20 | 138.8 |
| `POST /sessions/{id}/score/confirm` | 20 | 16.8 | 26.8 | 67.7 | 200×20 | 138.8 |

### 5 takes upload + analysis reads (wall 9.74 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions/{id}/takes` | 160 | 173.4 | 245.6 | 343.1 | 202×160 | 16.4 |
| `GET /sessions/{id}/takes/{take}/analysis` | 160 | 47.1 | 115.7 | 169.4 | 200×160 | 16.4 |
| `GET /sessions/{id}/takes/{take}/media` | 160 | 107.5 | 253.1 | 293.8 | 200×160 | 16.4 |
| `GET /sessions/{id}/takes/{take}/feedback` | 160 | 31.2 | 86.6 | 107.0 | 200×47, 409×113 | 16.4 |
| `POST /sessions/{id}/takes/{take}/feedback (rerun)` | 160 | 47.4 | 472.2 | 508.3 | 200×48, 409×112 | 16.4 |
| `GET /sessions/{id}/takes/{take}/tracks` | 160 | 26.5 | 87.8 | 112.1 | 404×160 | 16.4 |
| `POST /sessions/{id}/transposition` | 20 | 68.7 | 106.4 | 112.9 | 200×20 | 2.1 |

### 6 calibration (wall 46.03 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `GET /reference-notes` | 1 | 17.7 | 17.7 | 17.7 | 200×1 | 0.0 |
| `POST /sessions/{id}/calibration (live)` | 100 | 7145.0 | 13747.0 | 14339.8 | 200×100 | 2.2 |
| `POST /sessions/{id}/calibration/skip` | 100 | 34.2 | 105.1 | 203.7 | 200×100 | 2.2 |
| `GET /sessions/{id}/calibration` | 100 | 17.3 | 67.7 | 88.4 | 200×100 | 2.2 |

### 7 chat (wall 0.56 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions/{id}/chat (AI off)` | 160 | 16.2 | 109.5 | 314.3 | 200×160 | 286.8 |
| `GET /sessions/{id}/chat` | 160 | 11.7 | 94.0 | 234.9 | 200×160 | 286.8 |

### 8 camera check (wall 1.87 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions/{id}/camera-check` | 100 | 363.9 | 396.5 | 404.7 | 200×100 | 53.5 |

### 9 photo scans (wall 12.12 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions` | 24 | 22.3 | 47.3 | 50.8 | 201×24 | 2.0 |
| `POST /sessions/{id}/score/photo (not an image)` | 20 | 11.2 | 25.2 | 36.2 | 415×20 | 1.7 |
| `POST /sessions/{id}/score/photo (real photo)` | 4 | 7.5 | 12.0 | 12.0 | 202×4 | 0.3 |
| `GET /sessions/{id}/score/status` | 14 | 3.0 | 16.6 | 19.2 | 200×14 | 1.2 |

### 10a large takes (wall 36.53 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions` | 4 | 2.4 | 3.3 | 3.3 | 201×4 | 0.1 |
| `POST /sessions/{id}/score/file (builtin)` | 4 | 8.2 | 13.2 | 13.2 | 200×4 | 0.1 |
| `POST /sessions/{id}/score/confirm` | 4 | 1.6 | 2.7 | 2.7 | 200×4 | 0.1 |
| `POST takes (wav) 10 MB` | 1 | 17.0 | 17.0 | 17.0 | 202×1 | 0.0 |
| `GET analysis after big take` | 3 | 10.1 | 23.6 | 23.6 | 200×3 | 0.1 |
| `POST takes (wav) 50 MB` | 1 | 59.7 | 59.7 | 59.7 | 202×1 | 0.0 |
| `POST takes (wav) 200 MB` | 1 | 187.8 | 187.8 | 187.8 | 202×1 | 0.0 |
| `POST takes (wav) 201 MB` | 1 | 167.2 | 167.2 | 167.2 | 413×1 | 0.0 |

### 10b large score/photo/camera uploads (wall 0.76 s)

| route | n | p50 ms | p95 ms | max ms | status counts | req/s (phase) |
|---|---|---|---|---|---|---|
| `POST /sessions` | 9 | 1.3 | 271.6 | 271.6 | 201×9 | 11.9 |
| `POST score/file (.musicxml) 4 MB` | 1 | 5.3 | 5.3 | 5.3 | 422×1 | 1.3 |
| `POST score/file (.musicxml) 6 MB` | 1 | 5.1 | 5.1 | 5.1 | 413×1 | 1.3 |
| `POST score/file (.musicxml) 50 MB` | 1 | 36.5 | 36.5 | 36.5 | 413×1 | 1.3 |
| `POST score/file (.musicxml) 200 MB` | 1 | 152.0 | 152.0 | 152.0 | 413×1 | 1.3 |
| `POST score/photo 10 MB` | 1 | 34.0 | 34.0 | 34.0 | 202×1 | 1.3 |
| `POST score/photo 50 MB` | 1 | 41.9 | 41.9 | 41.9 | 413×1 | 1.3 |
| `POST score/photo 200 MB` | 1 | 145.7 | 145.7 | 145.7 | 413×1 | 1.3 |
| `POST camera-check 10 MB` | 1 | 8.2 | 8.2 | 8.2 | 413×1 | 1.3 |
| `POST camera-check 50 MB` | 1 | 35.3 | 35.3 | 35.3 | 413×1 | 1.3 |


## Memory of the server process


| start MB | peak MB | end MB | samples (every 2 s) | peak child-process MB (ffmpeg/homr) | process died |
|---|---|---|---|---|---|
| 165.3 | 1321.1 | 374.9 | 98 | 3951.6 | False |

| phase | peak RSS MB |
|---|---|
| start | 165.6 |
| 1 sessions create/get | 170.0 |
| 2 builtins/reference notes | 171.2 |
| 3 score upload/confirm/read | 324.1 |
| 5 takes upload + analysis reads | 939.1 |
| 6 calibration | 996.2 |
| 8 camera check | 871.9 |
| 9 photo scans | 873.1 |
| 10a large takes | 1321.1 |
| 10b large score/photo/camera uploads | 470.3 |
| 11 malformed | 558.5 |
| 12 session edge cases | 568.6 |
| 13 leak check | 569.4 |
| cooldown | 375.0 |

### Leak check: 1500 new sessions per round, 6 s idle, then RSS

| reading | RSS MB |
|---|---|
| before round 1 | 567.7 |
| after round 1 | 569.4 |
| after round 2 | 372.0 |
| after round 3 | 373.5 |
| after round 4 | 375.0 |

## Malformed and hostile inputs


Throwaway request right after a 5xx: {'sent': 2, 'dropped': 2}


| group | case | status | error code / body start |
|---|---|---|---|
| takes | wrong content-type text/plain | 415 | unsupported_type |
| takes | content-type missing/odd | 202 | {"take_id":"t1","status":"processing"} |
| takes | truncated webm (1000 bytes) | 202 | {"take_id":"t2","status":"processing"} |
| takes | truncated wav (header + half) | 202 | {"take_id":"t3","status":"processing"} |
| takes | zero-byte wav | 202 | {"take_id":"t4","status":"processing"} |
| takes | no file field | 422 | bad_request |
| takes | filename path traversal | 202 | {"take_id":"t5","status":"processing"} |
| takes | filename unicode + NUL | 202 | {"take_id":"t6","status":"processing"} |
| takes | mp4 type but wav bytes | 202 | {"take_id":"t7","status":"processing"} |
| takes | field bar_from='abc' | 422 | bad_request |
| takes | field bar_from='999999999999' | 422 | bad_request |
| takes | field bar_to='-1' | 422 | bad_request |
| takes | field tempo_bpm='nan' | 422 | bad_request |
| takes | field tempo_bpm='1e999' | 422 | bad_request |
| takes | field downbeat_s='inf' | 422 | bad_request |
| takes | field count_in_beats='2.5' | 422 | bad_request |
| takes | field kind='xxxxxxxxxxxx' | 422 | bad_request |
| takes | field bar_from='١٢' | 422 | bad_request |
| takes | field tempo_bpm='xxxxxxxxxxxx' | 400 | bad_request |
| takes | unknown take media | 404 | take_not_found |
| takes | take id traversal media | 404 | not_found |
| score file | wrong extension .exe | 415 | unsupported_type |
| score file | zero-byte .musicxml | 422 | bad_score_file |
| score file | truncated musicxml | 422 | bad_score_file |
| score file | not xml | 422 | bad_score_file |
| score file | entity expansion XML | 422 | bad_score_file |
| score file | filename path traversal | 200 | {"score_status":"scanned","bars":16,"dou |
| score file | filename unicode | 200 | {"score_status":"scanned","bars":16,"dou |
| score file | no file field | 422 | bad_request |
| score file | multipart without boundary | 400 | bad_request |
| score file | bad JSON | 422 | bad_request |
| score file | JSON list | 422 | bad_request |
| score file | builtin number | 422 | bad_request |
| score file | builtin null | 422 | bad_request |
| score file | builtin traversal | 404 | builtin_not_found |
| score file | builtin unknown | 404 | builtin_not_found |
| score file | builtin 5 MB string | 404 | builtin_not_found |
| score file | empty body | 422 | bad_request |
| score file | invalid UTF-8 | 422 | bad_request |
| score file | deeply nested | 500 | server_error |
| photo | zero bytes | 415 | unsupported_type |
| photo | text file | 415 | unsupported_type |
| photo | GIF | 415 | unsupported_type |
| photo | PDF | 415 | unsupported_type |
| photo | RIFF but not WEBP | 415 | unsupported_type |
| photo | 1-byte JPEG magic only | 202 | {"score_status":"scanning"} |
| photo | no file field | 409 | wrong_state |
| photo | truncated real JPEG | 202 | {"score_status":"scanning"} |
| photo | filename traversal (real photo) | 202 | {"score_status":"scanning"} |
| sessions/json/chat | POST /sessions bad JSON | 422 | bad_request |
| sessions/json/chat | POST /sessions empty body | 422 | bad_request |
| sessions/json/chat | POST /sessions instrument viola | 422 | bad_request |
| sessions/json/chat | POST /sessions instrument 5 MB | 422 | bad_request |
| sessions/json/chat | POST /sessions instrument number | 422 | bad_request |
| sessions/json/chat | POST /sessions form-encoded body | 422 | bad_request |
| sessions/json/chat | POST /sessions extra fields | 201 | {"session_id":"c943feef60854ca8812ecf891 |
| sessions/json/chat | POST /sessions JSON NaN | 422 | bad_request |
| sessions/json/chat | POST /sessions deeply nested | 400 | bad_request |
| sessions/json/chat | transposition semitones string | 422 | bad_request |
| sessions/json/chat | transposition semitones float | 422 | bad_request |
| sessions/json/chat | transposition semitones 99 | 422 | bad_request |
| sessions/json/chat | transposition semitones bool | 422 | bad_request |
| sessions/json/chat | transposition no body | 422 | bad_request |
| sessions/json/chat | transposition semitones 10**30 | 422 | bad_request |
| sessions/json/chat | chat empty message | 422 | bad_request |
| sessions/json/chat | chat spaces only | 422 | bad_request |
| sessions/json/chat | chat 1001 chars | 422 | bad_request |
| sessions/json/chat | chat 1 MB message | 422 | bad_request |
| sessions/json/chat | chat message number | 422 | bad_request |
| sessions/json/chat | chat unknown take_id | 404 | take_not_found |
| sessions/json/chat | chat huge take_id | 404 | take_not_found |
| sessions/json/chat | chat NUL + emoji | 200 | {"user_turn":{"id":"c1","role":"user","t |
| sessions/json/chat | chat message null | 422 | bad_request |
| calibration | no files | 422 | bad_request |
| calibration | click_at_s='nan' | 422 | bad_request |
| calibration | click_at_s='inf' | 422 | bad_request |
| calibration | click_at_s='-1' | 422 | bad_request |
| calibration | click_at_s='abc' | 422 | bad_request |
| calibration | click_at_s='1e999' | 422 | bad_request |
| calibration | click_at_s='' | 422 | bad_request |
| calibration | truncated ref_0 wav | 500 | server_error |
| calibration | zero-byte ref_1 | 422 | audio_unreadable |
| calibration | ref_2 text/plain | 415 | unsupported_type |
| calibration | ref_0 is 30 s long | 422 | bad_request |
| calibration | click is zero-byte | 422 | audio_unreadable |
| calibration | click_at_s beyond clip | 200 | ok |
| camera-check | zero bytes | 415 | unsupported_type |
| camera-check | text | 415 | unsupported_type |
| camera-check | truncated JPEG | 415 | unsupported_type |
| camera-check | JPEG magic only | 415 | unsupported_type |
| camera-check | real photo (baseline) | 200 | {"ok":false,"missing":["nose","left ear" |

## Session edge cases


Throwaway request right after a 5xx: {'sent': 4, 'dropped': 4}


| group | case | status | error code / body start |
|---|---|---|---|
| unknown/odd ids | GET /sessions/<unknown hex> | 404 | session_not_found |
| unknown/odd ids | GET /sessions/<unicode> | 404 | session_not_found |
| unknown/odd ids | GET /sessions/<unicode digits> | 404 | session_not_found |
| unknown/odd ids | GET /sessions/<encoded traversal> | 404 | not_found |
| unknown/odd ids | GET /sessions/<percent-NUL> | 404 | session_not_found |
| unknown/odd ids | GET /sessions/<300 chars> | 500 | server_error |
| unknown/odd ids | GET /sessions/<5000 chars> | 500 | server_error |
| unknown/odd ids | GET /sessions/<spaces> | 404 | session_not_found |
| unknown/odd ids | GET /sessions/<empty segment> | 404 | not_found |
| unknown/odd ids | GET /sessions/{id} (unknown id) | 404 | session_not_found |
| unknown/odd ids | POST /sessions/{id}/score/confirm (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/score (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/score/status (unknown id) | 404 | session_not_found |
| unknown/odd ids | POST /sessions/{id}/calibration/skip (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/calibration (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/chat (unknown id) | 404 | session_not_found |
| unknown/odd ids | POST /sessions/{id}/chat (unknown id) | 404 | session_not_found |
| unknown/odd ids | POST /sessions/{id}/transposition (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/takes/t1/analysis (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/takes/t1/media (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/takes/t1/feedback (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/takes/t1/tracks (unknown id) | 404 | session_not_found |
| unknown/odd ids | GET /sessions/{id}/feedback/f1/trace (unknown id) | 404 | session_not_found |
| unknown/odd ids | POST /sessions/{id}/score/file (unknown id) | 404 | session_not_found |
| unknown/odd ids | POST score/confirm <300 chars> | 500 | server_error |
| unknown/odd ids | POST score/confirm <5000 chars> | 500 | server_error |
| id case sensitivity | GET lowercase id | 200 | {"session_id":"7cf044d6ad954fa1a44f16c52 |
| id case sensitivity | GET UPPERCASE id | 200 | {"session_id":"7cf044d6ad954fa1a44f16c52 |
| id case sensitivity | skip calibration via UPPERCASE id | 200 | ok |
| id case sensitivity | GET calibration via lowercase id | 200 | ok |
| id case sensitivity | GET calibration via UPPERCASE id | 200 | ok |
| out of order / double actions | confirm before any score | 409 | wrong_state |
| out of order / double actions | take before confirm | 409 | wrong_state |
| out of order / double actions | transposition before confirm | 409 | wrong_state |
| out of order / double actions | read score before any score | 409 | wrong_state |
| out of order / double actions | status before any score | 200 | {"score_status":"none","score_error":nul |
| out of order / double actions | calibration (live) with no clips | 422 | bad_request |
| out of order / double actions | chat with no takes | 200 | {"user_turn":{"id":"c1","role":"user","t |
| out of order / double actions | first confirm | 200 | {"score_status":"confirmed","bars":16,"t |
| out of order / double actions | second confirm (double) | 409 | wrong_state |
| out of order / double actions | pick builtin after confirm | 409 | wrong_state |
| out of order / double actions | photo after confirm | 409 | wrong_state |
| out of order / double actions | feedback for unknown take | 404 | take_not_found |
| out of order / double actions | rerun feedback for unknown take | 404 | take_not_found |
| out of order / double actions | trace for unknown feedback | 404 | feedback_not_found |
| out of order / double actions | bar range beyond the score | 422 | bad_request |
| out of order / double actions | feedback while take still processing | 202 | {"take_id":"t1","status":"processing"} |
| out of order / double actions | rerun feedback right after upload | 409 | wrong_state |


### Concurrent writers on one session


| same-session write (20 at once) | result |
|---|---|
| builtin pick x20 | {"200": 20} |
| confirm x20 | {"200": 1, "409": 19} |
| calibration skip x20 | {"200": 20} |
| take upload x20 | {"202": 20} |
| take ids unique | "20 unique of 20 accepted" |
| chat x20 | {"200": 9, "409": 11} |
| transposition x20 | {"200": 20} |
| API vs disk take count | "api 20, disk 20" |
| take statuses on disk | {"done": 20} |
| chat turns stored | 18 |


Disk used by session folders: after load 974.7 MB, after large uploads 1248.5 MB (deleted at the end of the run).
