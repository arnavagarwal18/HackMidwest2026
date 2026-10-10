# LLD-3 change 3: Can't tell and transposition

Task brief from ARCHITECT-9 (M-240), saved verbatim.

Build LLD-3 change 3 "Can't tell and transposition": step 2 and step 4's can't-tell rule, plus POST /sessions/{id}/transposition with its rerun. Done when tests 6 and 7 below pass plus the full backend suite.

Context: FastAPI backend in backend/. Existing: backend/app/diagnosis/{config.py, errors.py, expected.py, align.py, mark.py, take_alignment.py (entry `align_take`)}; score routes and get_score in backend/app/score/; store API store.get(session_id) -> Session, store.update(session_id,key,value); errors via AppError(status,code,message) -> {error:{code,message}} (app/errors.py). mark.py may already compute some of the can't-tell rule; reuse, don't duplicate. Another coder is building timing (diagnosis/timing.py) in parallel; don't touch it. diagnosis.run (the full pipeline entry) doesn't exist yet (later change): the rerun should resolve `app.diagnosis.run` lazily at call time (getattr on the package) and skip with a log warning if absent; run reruns in a background thread/BackgroundTasks.

## Spec (LLD-3, verbatim)

- Step 2, transposition. If session.transposition is set, use it. Otherwise base = score file's written_transpose_semitones if present (source 'file'), else the instrument default (trumpet -2, violin 0, piano 0; source 'default'). On the session's first diagnosed take only, run steps 3-4 for each candidate in {base, 0, -2, -3, -7, -9} (deduplicated) and keep the base unless another candidate's line-up quality is at least base quality + 0.15; then source is 'detected'. Save to session.transposition; later takes reuse it (locked). Only POST /transposition changes it afterwards.
- Step 1 (context): sounding pitch = written pitch_midi + transposition semitones.
- Step 4 can't-tell: Line-up quality = ok count / expected count. Can't tell when quality < 0.4, or fewer than 50% of expected notes have a partner, or fewer than 3 expected notes; cant_tell_reason says which ('low_match', 'few_pairs', 'too_short'). When can't tell, results are still saved but no problems are ranked and tier1 is empty.
- Data: session.transposition = { semitones: int, source: 'file' | 'default' | 'detected' | 'user' } | null (set by the first diagnosed take). take.diagnosis has transposition {semitones, source}, alignment_quality (0-1), cant_tell: bool, cant_tell_reason: str|null.
- Contract: POST /sessions/{id}/transposition. Request JSON { semitones: int, -12 to 12 }. Response 200: { transposition: { semitones, source: 'user' }, rerun_takes: [take ids] }. It sets session.transposition, then reruns diagnosis on every take in the session in the background (each take's status goes back to 'diagnosed' when done; form flags are kept and re-ranked). Errors: 404 session_not_found; 422 bad_request (missing, not an integer, or out of range); 409 wrong_state (no score confirmed yet).
- Errors: No played notes or <3 expected notes -> diagnosis saved with cant_tell true, reason 'too_short' or 'low_match'; no problems. Bad transposition request -> 422 bad_request or 409 wrong_state; nothing changes.

## Tests (verbatim)

- Test 6 Can't tell: Random played notes against the score. Expect cant_tell true, reason 'low_match' or 'few_pairs', problems empty. A 2-note range gives reason 'too_short'.
- Test 7 Transposition detect: Trumpet take played at concert pitch of a score marked with no transposition and default -2: notes match only at 0. Expect switch to 0 with source 'detected' if quality improves by 0.15 or more; a second take reuses it without trying candidates. POST /transposition { semitones: -2 } returns 200, source 'user', and reruns the takes; { semitones: 20 } returns 422.

## What was built

- `diagnosis/mark.py` (change 1) already holds the can't-tell rule (`cant_tell_reason`); reused unchanged. Test 6 is in `tests/test_diagnosis_transposition.py`.
- `diagnosis/transposition.py`: `base_transposition(score, instrument)`, `detect_transposition(score, played, take, base) -> (transposition, alignment)`, and `align_with_transposition(score, played, take, instrument, locked)`, the entry the later `diagnosis.run` calls: pass `session.transposition` as `locked`; when it was None, save the returned transposition on the session.
- `diagnosis/rerun.py`: `rerun_takes(session_id, take_ids)` resolves `app.diagnosis.run` at call time and calls `run(session_id, take_id)` per take; skips with a warning if absent; a failing take is logged and the rest still run.
- `diagnosis/routes.py`: POST /sessions/{id}/transposition (registered in main.py). `Session.transposition` added to the store.

## Choices where the design was silent

- Detection compares each candidate's `alignment_quality` from `align_take`; if several candidates qualify, the best one wins (ties go to the base, then list order). A gain of exactly 0.15 counts (tiny float tolerance).
- `rerun_takes` is every take id in the session, as specified, whatever its status.
- Problems/tier1 don't exist yet, so "no problems when can't tell" is for the later problems step; `align_take` output has no `problems` key.
- Body validation runs before the session lookup, so a bad body to an unknown session is 422. `semitones` is a strict integer (no 1.5, "2" or true).
