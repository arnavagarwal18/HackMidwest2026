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
