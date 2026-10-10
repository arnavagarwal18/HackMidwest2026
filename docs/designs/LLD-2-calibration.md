# LLD-2 change 4: Calibration analysis and routes

Brief from ARCHITECT-8 (M-209), saved verbatim. Repo HackMidwest2026, built from main 1a2ebc7.

SPEC (LLD-2, verbatim):
- Reference notes per instrument, at sounding pitch (backend/app/takes/reference.py): violin D4 (293.66 Hz), A4 (440.00 Hz), E5 (659.26 Hz); trumpet B-flat 3 (233.08 Hz), F4 (349.23 Hz), B-flat 4 (466.16 Hz). Frequency rule: 440 x 2^((midi - 69) / 12).
- Calibration profile, stored in session.calibration: { source: 'live' | 'video' | 'default', calibrated: bool (false only for 'default'), pitch_offset_cents: float (mean of the reference notes' measured-minus-true cents; default 0), noise_floor_db: float (default -60), pickup_db: { low, mid, high } (each reference note's level relative to the middle one; default 0), latency_ms: float (default 0), instrument_offset_cents: float | null, notes: [ { asked: str, asked_hz: float, measured_hz: float | null, cents: float | null, problem: null | 'not_heard' | 'off_pitch' | 'too_noisy' } ] }.
- Calibration analysis (backend/app/takes/calibrate.py): for each ref clip, take the middle 60% of voiced frames, the median pitch in Hz, and cents = 1200 log2(measured / asked). Problems: no voiced frames for 0.5 seconds gives not_heard; more than 50 cents off gives off_pitch; noise (the quietest 10% of frames) within 15 dB of the note's level gives too_noisy. Any problem fails the whole calibration with the list. Otherwise: pitch_offset_cents is the mean of the 3 cents values; noise_floor_db is the quietest 10% level; pickup_db is each note's level minus the middle note's. Delay: find the first onset in the click clip; latency_ms = (onset - click_at_s) x 1000, clamped to 0 to 500. Instrument clips, if sent, give instrument_offset_cents the same way and never fail the calibration.
- POST /sessions/{id}/calibration. Multipart with ref_0, ref_1, ref_2 (one short audio clip per reference note, in order, 1 to 6 seconds each), click (a clip recorded while the front end played one click), click_at_s (float), optional inst_0, inst_1, inst_2. Clips may be webm/ogg/wav: decode via the imageio-ffmpeg binary to 16 kHz mono wav (reuse media_tools). Response 200 { profile } (source 'live'), saved to session.calibration. Errors: 404 session_not_found; 415 unsupported_type; 422 calibration_failed with body { error: {code:'calibration_failed', message}, notes: [ { asked, problem, cents } ] } listing each failing note; nothing saved on failure.
- POST /sessions/{id}/calibration/skip. {} -> 200 { profile } with source 'default' (the defaults above), saved. GET /sessions/{id}/calibration: 200 { profile } or { profile: null }. GET /reference-notes?instrument=violin: 200 [ { name, hz } ]; unknown instrument 422 bad_request.
- Learner message on failure names the note and problem, e.g. 'A4 was 70 cents off: is the tone page playing A4?'

Tests (from the plan, synthetic generated audio): the 3 reference notes 10 cents sharp give pitch_offset_cents 10 (within 2); a clip 70 cents off gives 422 with off_pitch for that note; a silent clip gives not_heard; a clip with loud noise gives too_noisy; a click clip with the click 120 ms after click_at_s gives latency_ms 120 (within 15); skip gives source 'default'; reference-notes returns 3 notes per instrument.

## Implementation notes

- Files: `reference.py` (notes), `calibrate.py` (analysis), `calibration_routes.py` (routes), `errors.py` (AppError gains optional `details`, merged into the body, used for the `notes` list).
- Note names are ASCII (`Bb3`, `Bb4`).
- not_heard: fewer than 50 voiced frames (0.5 s) in total, voiced = pYIN voiced and level at least -60 dB.
- A note has one problem; too_noisy is checked before off_pitch, because noise makes the pitch reading unreliable.
- pYIN's pitch grid reads a constant ~2.6 cents sharp, so the median pitch is refined with a spectral peak (parabolic interpolation) over the middle frames.
- Click onset: first 4 ms frame (1 ms hop) more than 12 dB above the clip's median level; no click found means 0 ms and a logged warning.
- Instrument clips: mean cents of those without a problem; unusable ones are logged and ignored; none usable means null.
- Clips over 6.5 s are rejected 422 bad_request; shorter ones simply end up not_heard.
