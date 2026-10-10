# LLD-3 change 2: Timing, drift and clean tempo (steps 5-6)

Code: `backend/app/diagnosis/timing.py` (+ tunables in `config.py`, `Session.clean_tempo` in `store.py`, `fit_line(points, min_points)` in `align.py`); tests in `backend/tests/test_diagnosis_timing.py`.

## Brief (from ARCHITECT-9)

Build steps 5-6 incl. the fitted grid. Done when tests 4, 5 and 8 pass plus the full backend suite. Unit-test error_rate (uncertain excluded) and clean tempo (fallback 70%).

- Step 3 grid (in align.py), as revised by r2 below: if take.downbeat_s is not null, grid kind 'metronome' with offset_s = downbeat_s (originally downbeat_s - latency_s) and sec_per_beat = 60 / target_bpm, else kind 'fitted' using the fit. Expected_onset_s comes from the grid.
- Step 5, timing. For ok and wrong notes, timing_ms = (played onset_s - latency_s - expected_onset_s) x 1000 on the metronome grid, without latency_s on the fitted grid (r2; the original subtracted it always); positive is late. latency_s is take.calibration latency (0 if not calibrated). A note is late if timing_ms > 80, early if < -80. played_bpm = 60 / fitted sec_per_beat (from step 3's fit even on a metronome grid). Per bar: local tempo by linear regression of played onset on expected beat over that bar's ok notes (needs >= 2), local_bpm = 60 / slope; drift_pct = (local_bpm - target_bpm) / target_bpm x 100; rushing if > +5, dragging if < -5, else steady; null with fewer than 2 notes.
- Step 6, error rate and clean tempo. error_rate = (wrong + missed + late + early) / expected, uncertain notes excluded from both sides. After each take, for its bar range key '{bar_from}-{bar_to}', clean tempo = the highest played_bpm among the session's takes on that range with error_rate <= 0.10 and not can't tell; if none, 70% of this take's played_bpm. Saved to session.clean_tempo.
- Data: session.clean_tempo = { '{bar_from}-{bar_to}': float }. NoteResult.timing_ms: float | null (positive is late). BarResult: { id, bar, expected, ok, wrong, missed, extra, uncertain, mean_timing_ms, local_bpm, drift_pct (positive is faster), drift: 'rushing'|'dragging'|'steady'|null }. take.diagnosis has grid {kind, offset_s, sec_per_beat}, played_bpm, target_bpm, latency_ms, error_rate. Bar ids 'b:{take}:{bar}'. API field latency_s = calibration profile latency_ms / 1000.
- Tests: 4 Late notes (bar 3 shifted 100 ms: timing about +100, 4 notes late, mean about 100; the 'late' problem itself is change 4); 5 Rushing (bars 5-6 at 10% faster: drift 'rushing', about +10%); 8 Fitted grid (upload take, downbeat_s null, starts 2.3 s in at 90 BPM against target 80: grid 'fitted', played_bpm about 90, timing near 0).

## API

`add_timing(result, played, take) -> dict`: `result` is `align_take`'s output, `played` the same played notes, `take` the same take dict. Returns `result` with `timing_ms` filled in on every note, plus `bars`, `played_bpm`, `target_bpm`, `latency_ms`, `error_rate`. Pure; `align_take` is untouched.

`save_clean_tempo(session_id, take, diagnosis) -> float`: works out the clean tempo from `session.takes` (other takes' stored `diagnosis`: `played_bpm`, `error_rate`, `cant_tell`) and the take's own new diagnosis, and saves it with `store.update(session_id, 'clean_tempo', ...)`. `clean_tempo_for` is the pure part.

## Choices where the brief was silent

- played_bpm with no step 3 fit (fewer than 3 same-midi pairs): the grid's tempo (target on a metronome grid).
- timing_ms is rounded to 2 decimals; late/early is judged on the rounded value.
- mean_timing_ms is the mean over the bar's notes that have timing (ok and wrong).
- error_rate is the literal sum of counts, so a wrong note that is also late counts twice; None when every expected note is uncertain (a None rate never counts as clean).
- Per-bar regression uses `fit_line` (rejects a flat or backwards slope, so such a bar gets null drift).
- A take whose stored `diagnosis` is missing is ignored by clean tempo; the take being diagnosed is always counted from the diagnosis passed in, not its stored copy.
- `Session.clean_tempo` added as `dict` defaulting to `{}`; old session.json files still load.

## Latency (LLD-3 r2, replaces the original spec's double count)

The original spec subtracted latency twice on the metronome grid (offset_s = downbeat_s - L, then step 5 minus L, so L cancelled) and subtracted it from a fitted grid that already contains it (every on-beat note came out at -L). Found by CODER-15 with numeric checks; ARCHITECT-9 accepted it. New rule, one subtraction:

- Step 3, metronome grid: offset_s = downbeat_s (no latency term). `build_grid` no longer takes latency_s.
- Step 5, metronome grid: timing_ms = (played onset_s - latency_s - expected_onset_s) x 1000.
- Step 5, fitted grid: timing_ms = (played onset_s - expected_onset_s) x 1000 (the fit already contains the latency).
- `latency_ms` in the diagnosis is still the calibration latency.

Tests: a take delayed only by its latency is on time (metronome); bar 3 +100 ms with latency 0.1 gives bar-3 timing about 0 and no late notes (the other 12 notes read -100, early, as the whole take is then 100 ms too soon after correction); fitted grid at latency 0.1 still reads about 0.
