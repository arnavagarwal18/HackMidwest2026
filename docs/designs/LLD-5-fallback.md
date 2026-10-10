# LLD-5 change 3: Fallback, records and routes

Brief from ARCHITECT-9 (M-251). Code: `backend/app/agents/{fallback,run,trace,routes}.py`, a hook in `backend/app/takes/pipeline.py`.

## Task

Build `fallback.py`, `run.py` (`run_feedback`; only the AI_ENABLED=false / fallback path is required now, the Orchestrator/Coach/Planner come later: when AI_ENABLED is true and no orchestrator exists, use the fallback with reason 'model_error' and log it), `GET/POST /sessions/{id}/takes/{take}/feedback`, and the take-pipeline hook that calls `agents.run_feedback` after diagnosis (and form for video) for purpose 'take', then sets status 'done'. `run_feedback` writes `data/sessions/{id}/{fb}_trace.json` with at least a 'fallback' event. The trace route and TraceHook are a later change.

## Spec (LLD-5)

- Feedback record in `session.feedback['fb{n}']`: `{ id, take_id, created_at, mode: 'ai' | 'fallback', fallback_reason: null | 'timeout' | 'model_error' | 'checker_rejected' | 'disabled' | 'cant_tell', cant_tell: bool, tier1: [Sentence] (copied from LLD-3), sentences: [CoachSentence plus checked: true], dropped: [ { text, reasons: [str] } ], plan_id: str | null, check: { coach_tries, planner_tries, claims_checked, claims_failed, sentences_dropped }, duration_ms: int }`. Plan record in `session.plans['pl{n}']`: `{ id, take_id, feedback_id, mode: 'ai' | 'fallback', exercises: [Exercise] }`.
- Exercise: `{ id: 'ex{n}' (assigned by code), title, text (<=40 words), bar_from, bar_to, start_bpm, target_bpm, step_bpm (2-10), reps_to_pass (1-5), pass_mark: { max_errors: int, max_mean_timing_ms: float|null, form_rule: str|null }, problem_ids: [str], claims: [Claim] }`.
- Trace event: `{ t_ms, agent: 'orchestrator'|'coach'|'planner'|'checker', event: ...|'fallback', name, detail (<=500 chars), duration_ms }`.
- `agents.run_feedback(session_id, take_id) -> feedback_id`. Called by LLD-2's pipeline runner after `diagnosis.run` and (for video) `form.run`; it then sets the take's status to 'done'. Never raises: any failure produces a fallback feedback record. Total time limit 30 s.
- `GET /sessions/{id}/takes/{take}/feedback`: 200 the take's latest Feedback record plus `plan: Plan | null`. 404 session_not_found or take_not_found; 409 wrong_state 'Feedback not ready.' while the take status is not 'done'.
- `POST /sessions/{id}/takes/{take}/feedback`: request `{}`. Runs `run_feedback` again and returns 200 with the new Feedback and plan, within 35 s. 404 session_not_found or take_not_found; 409 wrong_state (take not yet 'diagnosed' or a feedback run already in progress for this take). One run per take at a time.
- `run_feedback` flow: 1) read the take; if AI_ENABLED is false go to the fallback with reason 'disabled'. 2) create feedback id and trace. 3-6) agents (later). 7) build the Feedback and Plan records (code assigns exercise ids), save via `store.update` on the feedback and plans keys, call `practice.init_plan(session_id, plan_id)` (LLD-6; resolve lazily, skip with warning if absent), write the trace file, return the id. Any exception or timeout goes to the fallback with reason 'model_error' or 'timeout'.
- Fallback. Sentences: LLD-3's tier 1 template sentences only, marked mode 'fallback'. Plan: for each tier 1 problem (at most 3), an exercise on its bars from the clean tempo (or 70% of target) to the target, step 4 BPM, reps_to_pass 2, pass mark max_errors 0 plus max_mean_timing_ms 50 for late/early/rushing/dragging problems or form_rule for form problems; then one whole-range exercise at the target tempo with max_errors 1. With cant_tell: no sentences besides the can't-tell message, and one whole-range exercise at 70% of target. If only one agent failed, keep the other's accepted output and use the fallback for the missing part.
- Errors: can't tell -> retake plan as above (reason 'cant_tell'); a failed take gets no feedback run (runner skips it). Second POST while running -> 409 wrong_state 'Feedback already running.' If only the trace write fails, feedback is still saved; if the feedback record can't be saved, take status 'failed' with error storage_error.

## Tests required

Fallbacks: AI_ENABLED false gives mode 'fallback', reason 'disabled', tier 1 sentences and a rule plan with one exercise per tier 1 problem plus a whole-range one. A can't-tell take gives no coach call and one 70% retake exercise. The rule plan passes `check_plan`. Contracts (TestClient): GET 409 before 'done', 200 after; POST twice at once: second gets 409. Pipeline: the runner calls `run_feedback` for purpose 'take' and the take ends 'done'; a failed take is skipped.

## Decisions made while building

- `run_feedback(session_id, take_id, *, wait=True)`: the pipeline queues behind a running run; the POST route passes `wait=False` and gets 409 'Feedback already running.'. The pipeline, not `run_feedback`, sets status 'done', and leaves a take that `run_feedback` marked failed (storage_error) as failed.
- `app.agents.config` (AI settings) is not on main yet: `run.ai_enabled()` imports it lazily and treats AI as off, with a warning, while it is missing. Tests patch `run.ai_enabled`.
- Take data is read as stored on the take: `take['diagnosis']` (LLD-3 shape) and `take['form']['flags']` (assumed LLD-4 shape). A take with no diagnosis gets no sentences and one whole-range exercise. History for the clean tempo is the session's earlier diagnosed takes on the same bars.
- A take with no tier 1 problems gets only the whole-range exercise (the Checker wants 2 to 4, so this plan would not pass `check_plan`).
- The can't-tell case takes precedence over 'disabled' as the reason. Fallback sentences carry `jump.bar` of the first cited problem's first bar.
- Exercise ids 'ex{n}' count across all the session's plans. The plan is saved before the feedback.
- No timeout machinery yet (`TIME_LIMIT_S = 30` is for the agents); the rule plan takes milliseconds.
