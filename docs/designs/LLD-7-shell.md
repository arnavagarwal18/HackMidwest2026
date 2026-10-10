# LLD-7 change 1: shell, api.js, state, router and mocks

Verbatim from the approved design (LLD-7 "Web front end", item 01a12755-9d89-77a3-aee9-1f9c66c5f08e), as sent by ARCHITECT-7 (M-131).

FILES: frontend/index.html (single page, hash routes #/start, #/score, #/calibrate, #/take, #/results/{take}, #/exercise/{ex}, #/progress, #/trace/{fb}); frontend/tone.html (placeholder now); frontend/js/{api.js, state.js, router.js, screens/*.js (placeholder screen per route)}; frontend/css/app.css; frontend/mock/*.json (one saved response per route, used when the URL has ?mock=1).

STATE (frontend/js/state.js, one JS object, lost on reload except session_id kept in localStorage): { session_id, instrument, score: {status, bars, tempo_bpm, time_signature}, calibration: profile|null, take_setup: {bar_from, bar_to, tempo_bpm, kind, count_in_beats (default 4), metronome_on (default false)}, current_take_id, current_feedback_id, current_exercise_id }.

API.JS: fetch, JSON, multipart field 'file'; errors come as { error: { code, message } } -> throw; screen shows a red banner with error.message, keeps inputs, no auto-retry. fetch rejects (server down) -> banner 'Can't reach the app server on this laptop' with Retry that repeats the last request once per press. With ?mock=1, read frontend/mock/*.json instead.

RELOAD: on load read session_id from localStorage, GET /sessions/{id}, go to #/score if score_status != 'confirmed' else #/take. 404 session_not_found -> clear localStorage, go to #/start with 'Your earlier session was not found; starting fresh.'

ROUTES and shapes for mocks (all JSON):
- POST /sessions {instrument:'violin'|'trumpet'} -> {session_id, instrument}. GET /sessions/{id} -> {session_id, instrument, score_status ('none'|'scanning'|'scanned'|'failed'|'confirmed'), has_calibration, take_ids:[str]}.
- GET /builtins?instrument= -> [{piece_id, title, instrument, bars}]. POST /sessions/{id}/score/photo (multipart) -> 202 {score_status:'scanning'}. GET .../score/status -> {score_status, score_error: null|'scan_failed'|'no_notes'|'scan_timeout', bars, doubtful_bars:[{bar, homr_text, reader_text}], double_checked, warnings:[str]} (poll 2 s). POST .../score/file (multipart or {builtin}) -> {score_status:'scanned', bars, doubtful_bars, double_checked, warnings}. POST .../score/confirm -> {score_status:'confirmed', bars, tempo_bpm, time_signature:[4,4]}.
- GET /reference-notes?instrument= -> [{name, hz}] (violin D4 293.66, A4 440.00, E5 659.26). POST .../calibration (multipart ref_0..2, click, click_at_s) -> {profile}; 422 calibration_failed with notes:[{asked, problem, cents}]. POST .../calibration/skip -> {profile} (source 'default'). GET .../calibration -> {profile} or {profile:null}. Profile: {source, calibrated, pitch_offset_cents, noise_floor_db, pickup_db:{low,mid,high}, latency_ms, instrument_offset_cents, notes:[...]}.
- POST /sessions/{id}/takes (multipart file + kind, source, bar_from, bar_to, tempo_bpm, count_in_beats, downbeat_s) -> 202 {take_id, status:'processing'}.
- Later routes (placeholder mocks): GET .../takes/{take}/analysis {status: 'processing'|'transcribed'|'diagnosed'|'done'|'failed', error, form_status, ...}; GET .../takes/{take}/media; GET .../takes/{take}/tracks; GET/POST .../takes/{take}/feedback; GET /sessions/{id}/feedback/{fb}/trace; POST /sessions/{id}/camera-check; GET .../exercises/{ex}; POST .../exercises/{ex}/reps; GET .../reps/{rep}; GET .../progress; GET /lan-address {url}.
