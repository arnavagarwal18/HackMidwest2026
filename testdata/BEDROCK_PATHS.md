# Every code path that calls Bedrock

Found by searching `backend/app` for `build_bedrock_model`, `build_agent_model`, `BedrockModel`, `boto3` and `strands` (checked 2026-10-11 on main d6da09a). Settings are named only; no value is recorded here. Every path also needs `AI_ENABLED` true.

**Never run live: all of them.** Bedrock access was never available. Evidence: `git log` has no result of a live run; `backend/app/agents/samples/live_trace.json`, which `live_check` would write, does not exist; `RESULTS_*.md` and `qa/` all record `AI_ENABLED=false`; every AI test uses a scripted or stubbed model. So the real Strands-to-Bedrock request and response shapes (tool calls, structured output, image input, `max_tokens`) are untested for every path below.

"Fake-model test" means a test that runs the path on a scripted or stubbed model, with no AWS.

| Path (module:function) | Entry | Model setting | Fake-model test | Live? | Smoke script row |
|---|---|---|---|---|---|
| `app/score/reader_agent.py:read_score` (`_ask_model`: Strands `Agent` on a Bedrock vision model, image in, `Reading` structured output) | `scan_job._run_reader` from `POST /sessions/{id}/score/photo` | `BEDROCK_VISION_MODEL` | Yes, `test_score_reader_agent.py` and `test_scan_job_reader.py` stub `_ask_model`; `Agent` is faked, so the real structured-output call is untested | never | `score reader (vision)` |
| `app/score/referee/agent.py:build_strands_agent` / `run` (vision model with four tools, settles bars where homr and the reader disagree) | `scan_job._record_success` from the same photo scan, only when a bar is doubtful | `BEDROCK_VISION_MODEL` | Partly: `test_referee_run.py` and `test_scan_job_referee.py` use a stub agent; `test_referee_strands.py` builds the real agent but never calls it | never | **none** (needs a bar where homr and the reader disagree; see gaps) |
| `app/agents/ai_run.py:run_agents` with `orchestrator.py:build_orchestrator` (text model, tool calls, runs the Coach and Planner as sub-agent tools) | `run.run_feedback` from `takes/pipeline._give_feedback` after a take, and `POST /sessions/{id}/takes/{take}/feedback` | `BEDROCK_TEXT_MODEL` (via `model.build_agent_model`) | Yes, `test_run_ai.py`, `test_agent_token_caps.py`, `test_live_check.py` | never | `feedback: coach` / `feedback: planner` (latency is the whole run) |
| `app/agents/coach.py:build_coach_agent` (`submit_feedback`) | the Orchestrator's `coach` tool | `BEDROCK_TEXT_MODEL` | Yes, `test_coach_hook.py`, `test_run_ai.py` | never | `feedback: coach` |
| `app/agents/planner.py:build_planner_agent` (`submit_plan`) | the Orchestrator's `planner` tool | `BEDROCK_TEXT_MODEL` | Yes, `test_planner_hook.py`, `test_run_planner.py` | never | `feedback: planner` |
| `app/agents/checker.py:check_feedback` / `check_plan` and `hooks.py:CheckerHook` (no model of its own: plain Python judging each submit; the hook sits on the Coach, Planner and Instructor agents) | each `submit_*` tool call | none | Yes, `test_checker_feedback.py`, `test_checker_plan.py`, `test_coach_hook.py` | never (with a real model's tool-call output) | the `checker` column on the three rows above and the chat row |
| `app/agents/chat_run.py:answer` with `instructor.py:build_instructor_agent` (`submit_reply`, `chat_checker.check_reply`) | `POST /sessions/{id}/chat` (`chat_routes.post_chat`) | `BEDROCK_TEXT_MODEL` | Yes, `test_chat_routes.py`, `test_chat_checker.py`, `test_instructor_*.py` | never | `instructor chat` |
| `app/agents/smoke.py:main` (`python -m app.agents.smoke`: one text call, one tiny-PNG vision call, `build_bedrock_model`) | command line | `BEDROCK_TEXT_MODEL`, `BEDROCK_VISION_MODEL` | Partly: `test_agents_config.py` stubs `_ask` for the settings and error lines | never | not run by the script (a cheaper check of the two model IDs and access) |
| `app/agents/live_check.py:run_live_check` (`python -m app.agents.live_check`: the feedback run once, single shot, saves a trace) | command line | `BEDROCK_TEXT_MODEL` | Yes, `test_live_check.py` | never | the same path as the feedback rows |
| `app/agents/model.py:build_bedrock_model` / `build_agent_model` / `with_max_tokens` (the builders; they create the `boto3` session and `BedrockModel`, and make no call themselves) | called by every path above | `BEDROCK_REGION`, `AWS_PROFILE` (optional), plus the model setting each caller passes | Yes, `test_agents_model.py`, `test_agent_token_caps.py` build the model without calling it | never | all rows |

Settings read by the loader (`app/agents/config.py:get_settings`): `AI_ENABLED`, `BEDROCK_REGION`, `BEDROCK_TEXT_MODEL`, `BEDROCK_VISION_MODEL`, `AWS_PROFILE`.

## Gaps in the smoke script

- **Referee**: runs only inside a photo scan, and only when homr and the reader disagree on a bar. The script does not force that, so a clean run can pass without calling it. If the Reader row passes and a real photo scan (`scripts/e2e_real.py` with a photo, AI on) reports `referee.status` as `done`, the referee ran; otherwise it is still unproven.
- **Feedback latency** is one number for the whole run (Orchestrator, then Coach and Planner in parallel); per-stage times are in `{feedback_id}_trace.json` in the temporary session folder, or from `python -m app.agents.live_check`.
- The script uses the Ode to Joy take (`testdata/ode_to_joy/score.musicxml` with `ode_to_joy_trumpet11.mp4`, bars 1-16, quarter = 100), not `trumpet_video1`, because `e2e_real.py` can upload a MusicXML score without a homr photo scan.
