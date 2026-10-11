# HackMidwest 2026: team TODO

The one shared checklist for all 5 of us. Each person's Yui works from this file: when you finish an item, change `[ ]` to `[x]` in the same commit that does the work, and push to main. Add new items under your own name.

State when written: main b6a27a0 (2026-10-11 04:40 UTC). Smoke tests on main: 91 passed, 3 skipped, 0 failed.

## Xavier (ThinkPad X1 Carbon, Intel Core Ultra 7, 32 GB): integration
- [x] Merge the rushing and missed-notes fix (LLD-3 r4-B, branch task/TASK-41) to main
- [ ] Re-run the key search, check the feedback updates, and record it in testdata/RESULTS_integration.md (LLD-3 r4-D)
- [ ] Confirm Jameson's one-line fault descriptions (LLD-4 comment 01a128f9)
- [ ] Final full test run on main after everyone's merges
- [ ] Final end-to-end sign-off
- [ ] Optional clips: good posture that then goes bad; bad posture from the side; front-view good/bad pair; puffed cheeks close up; take 5 side view with hips in frame

## Jameson (MacBook Pro M5, 24 GB): heavy posture compute
- [ ] LLD-4 change 11: fixed limits on head pitch, neck angle and back angle in backend/app/form/, set from testdata/youtube/posture_stats.csv (about p1/p99 of good players, loose enough for camera angle and body build); keep the baseline rules for drift during the take
- [ ] The 3 good-posture clips (testdata/form/good_posture_*.mp4) no longer raise trumpet_head_down; remove their known_false_positive marks in testdata/form_expectations.json
- [ ] Xavier's take 5 front and side clips still give their expected flags; `pytest backend/tests/test_form*.py` passes
- [ ] Write testdata/youtube/fault_candidates_reviewed.csv (one-line fault per video)
- [ ] Merge or delete branch origin/task/TASK-45
- [ ] Push to main and post the results on LLD-4 comment 01a128f9 for Caleb

## Caleb (AMD Ryzen 9 270, 16 GB): review and clean-up
- [ ] Merge or delete branch origin/task/TASK-10
- [ ] Review change 11 against the existing posture rules (limits loose enough for camera angle and body build; drift rules kept; `pytest backend/tests/test_form*.py`)
- [ ] Reply on LLD-4 comment 01a128f9 with approve or the blocking issues

## Arnav (MacBook Air M2, 16 GB, has AWS): live AI checks
- [ ] Set backend/.env: AI_ENABLED=true, BEDROCK_REGION, BEDROCK_TEXT_MODEL, BEDROCK_VISION_MODEL, AWS_PROFILE (never commit .env)
- [ ] Run `python backend/scripts/live_bedrock_smoke.py`
- [ ] Score referee on 2 real phone photos of sheet music: is the 0.7 confidence floor right?
- [ ] Coach and planner on a real take (testdata/reference Ode to Joy): the output passes the checker
- [ ] Instructor chat: 3 questions about that take; each answer cites a bar or time
- [ ] Record results in testdata/RESULTS_live.md and push to main
- [ ] Merge or delete branch origin/task/TASK-17

## Rikhil (MacBook Air M5, 16 GB): front end and full run
- [ ] Decide whether frontend/js/results/autokey_run.js writeFeedbackAgain (5 retries on HTTP 409) is still needed now that the server does the key search; remove it if not (LLD-3 r4-C)
- [ ] After Arnav's live checks pass: one full end-to-end run with AI on (photo, confirm score, record take, feedback, plan, chat) on a laptop with AWS access
- [ ] Push fixes for every screen that breaks

## Later (waiting on Xavier)
- [ ] Phone recording over the venue Wi-Fi (wait until Xavier brings it up)
