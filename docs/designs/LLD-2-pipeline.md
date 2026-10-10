# LLD-2 change 3: Pipeline runner

Brief from ARCHITECT-8 (M-208), saved as given.

Build on `backend/app/takes/pipeline.py` `run_take_pipeline(session_id, take_id)` (per-session lock, `extract_audio`, TODO hook for transcribe, diagnosis.run and form.run), `transcribe.transcribe(wav_path, instrument, profile) -> list[PlayedNote]` (NoNotesHeard / UnknownInstrument / AudioUnreadable, all AppError subclasses), `take_store.add_take/update_take`, and `store.get/update/session_dir`.

## Spec (LLD-2, verbatim)

Pipeline order: extract audio, calibrate from the video if it applies, transcribe (status 'transcribed'), diagnosis.run (status 'diagnosed'). For a mic take, status then becomes 'done'. For a video, form_status becomes 'processing', form.run runs, form_status becomes 'done' or 'failed', and status becomes 'done' either way. Note results are readable from 'diagnosed' on. Any exception in a step before form sets status 'failed' and error to that step's code, and logs the traceback. Error codes in take.error: no_audio_track, no_notes_heard, too_long, decode_failed, transcription_failed (transcriber throws anything unexpected -> transcription_failed). PlayedNote list is stored in take.notes and saved as {take_id}_notes.json in the session folder. Calibration profile = session.calibration if set, else the default { source:'default', calibrated:false, pitch_offset_cents:0, noise_floor_db:-60, pickup_db:{low:0,mid:0,high:0}, latency_ms:0, instrument_offset_cents:null, notes:[] }; set take.calibrated from it. Video calibration (from uploads) is a later change: leave a clearly named no-op hook that returns (None, 0.0) for (profile, calib_end_s).

## Interfaces

LLD-3 provides diagnosis.run(session_id, take_id) and LLD-4 provides form.run(session_id, take_id). They don't exist yet: resolve them lazily (import app.diagnosis.run / app.form.run at call time; if the module or function is missing, log a warning and skip that step: diagnosis-missing still advances to 'diagnosed', form-missing sets form_status 'none'), and make them injectable for tests.

## Tests (from the plan)

With diagnosis and form stubbed, a mic take goes processing -> transcribed -> diagnosed -> done (record the sequence); a video take also sets form_status processing then done; a failing form stub sets form_status 'failed' while status is 'done'; transcriber stub throwing RuntimeError gives transcription_failed; NoNotesHeard gives no_notes_heard; a failing diagnosis stub gives status 'failed' with a diagnosis error code.

## Implementation notes (not part of the approved design)

- Steps live in `backend/app/takes/pipeline_steps.py`; `pipeline.py` sequences them. `run_take_pipeline` takes keyword-only `transcriber`, `diagnose`, `check_form` to inject stubs.
- Diagnosis failures store `diagnosis_failed`. `AudioUnreadable` from the transcriber stores `decode_failed`; `UnknownInstrument` and anything else store `transcription_failed`.
- A form step that raises never fails the take: form_status 'failed', status 'done'.
- A `ModuleNotFoundError` for any module other than the step's own is not hidden (a real broken import surfaces as `pipeline_error`).
