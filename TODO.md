# HackMidwest 2026: team TODO

The one shared checklist for all 5 of us. Each person's Yui works from this file: when you finish an item, change `[ ]` to `[x]` in the same commit that does the work, and push to main. Add new items under your own name.

State when written: main b6a27a0 (2026-10-11 04:40 UTC). Smoke tests on main: 91 passed, 3 skipped, 0 failed.

## Xavier (ThinkPad X1 Carbon, Intel Core Ultra 7, 32 GB): integration
- [x] Merge the rushing and missed-notes fix (LLD-3 r4-B, branch task/TASK-41) to main
- [x] Re-run the key search, check the feedback updates, and record it in testdata/RESULTS_integration.md (LLD-3 r4-D)
- [ ] Confirm Jameson's one-line fault descriptions (LLD-4 comment 01a128f9)
- [ ] Final full test run on main after everyone's merges
- [ ] Final end-to-end sign-off
- [ ] Optional clips: good posture that then goes bad; bad posture from the side; front-view good/bad pair; puffed cheeks close up; take 5 side view with hips in frame
- [x] Fault videos, flags with the new limits (once TEAM-10's testdata/youtube/fault_candidates_reviewed.csv is on main; no existing script batch-runs the flags, so first add a small backend/scripts/ one that does what backend/tests/test_form_real_video.py does with `add_form_take` and `form.run`, trumpet only): from the repo root fetch the 20 videos with `backend/.venv/bin/python backend/scripts/fetch_youtube.py --list testdata/youtube/fault_candidates.csv` (Windows: `backend/.venv/Scripts/python`; one is unavailable, FSsO_-LrqE4, so exit code 1 is expected; the videos stay git-ignored under testdata/youtube/fault_videos/), run it over them with main at b811213 or later, and compare each video's flags with fault_candidates_reviewed.csv. Done: a per-video match table appended to testdata/RESULTS_form_runs.md and committed, and a summary posted on LLD-4 comment 01a128f9 (done 2026-10-11, see testdata/RESULTS_form_runs.md; LLD-4 summary still to post)

## Jameson (MacBook Pro M5, 24 GB): heavy posture compute
- [x] LLD-4 change 11: fixed limits on head pitch, neck angle and back angle in backend/app/form/, set from testdata/youtube/posture_stats.csv (about p1/p99 of good players, loose enough for camera angle and body build); keep the baseline rules for drift during the take
- [x] The 3 good-posture clips (testdata/form/good_posture_*.mp4) no longer raise trumpet_head_down; remove their known_false_positive marks in testdata/form_expectations.json
- [x] Xavier's take 5 front and side clips still give their expected flags; `pytest backend/tests/test_form*.py` passes
- [x] Write testdata/youtube/fault_candidates_reviewed.csv (one-line fault per video)
- [x] Merge or delete branch origin/task/TASK-45
- [x] Push to main and post the results on LLD-4 comment 01a128f9 for Caleb
- [x] Instructor chat: force/re-prompt submit_reply when Haiku answers in plain text (LLD-5 change 7, live bug H-179)
- [ ] Why the fault-video misses were missed. Pull origin/main (78c7977+). The fault-video run found 4 of 19 keyed faults and missed 13 (trumpet_head_down missed 8, trumpet_bell_angle missed 4); see testdata/RESULTS_form_runs.md section "Fault videos with change-11 limits (2026-10-11)", testdata/youtube/fault_flags.csv and fault_keys.csv. For each miss run `backend/scripts/fault_flags.py --only <video id>` (AI off, one video at a time) and read the measures in the key window (head_drop/head_pitch/bell measure, view detected, visibility, baseline). Classify each: limit too loose / baseline absorbed fault / wrong view / not visible / run under 1.0 s / doubtful key; propose the smallest rule or limit change that catches it without flagging good players. Do NOT edit backend/app/form/config.py (TASK-51 on Xavier's laptop is changing limits). Done: new section "Why the fault-video misses were missed (2026-10-11)" in testdata/RESULTS_form_runs.md, reviewed, merged to main and pushed; 5-line summary posted as a reply on LLD-4 comment 01a128f9
- [x] (Optional, ask Rikhil first) Front-end labels for the new flags trumpet_elbows_wide and trumpet_bell_angle in frontend/js/results/overlay/flag_points.js and its mocks. Done: labels show for both flags; front-end tests pass; merged to main

## Caleb (AMD Ryzen 9 270, 16 GB): review and clean-up
- [x] Merge or delete branch origin/task/TASK-10
- [x] Review change 11 against the existing posture rules (limits loose enough for camera angle and body build; drift rules kept; `pytest backend/tests/test_form*.py`)
- [x] Reply on LLD-4 comment 01a128f9 with approve or the blocking issues
- [x] Posture stats on the full video length, off the 1500 MB memory cap (good-set videos; fetch first with `backend/.venv/bin/python backend/scripts/fetch_youtube.py` from the repo root): the script has no output option and always writes testdata/youtube/posture_stats.csv and the "Good-posture statistics" section of testdata/RESULTS_form_runs.md, so from the repo root run `backend/.venv/bin/python backend/scripts/posture_stats.py --cap-s 100000 --max-seconds 0` (`--max-seconds` lands with TASK-49 and 0 means no cap; until it lands, omit it, since `--cap-s 100000` alone covers the whole video), then `mv testdata/youtube/posture_stats.csv testdata/youtube/posture_stats_full.csv` and `git checkout testdata/youtube/posture_stats.csv` so the original is never overwritten (put the new RESULTS section aside before the checkout, as only the comparison below goes in). Done: posture_stats_full.csv committed, and a short p1/p99 comparison against posture_stats.csv added to testdata/RESULTS_form_runs.md
- [x] On Windows, run the form tests and the real end-to-end run: from the repo root `backend/.venv/Scripts/python -m pytest backend/tests/test_form*.py`, then with the server running (default http://127.0.0.1:8000) from backend/ `.venv/Scripts/python scripts/e2e_real.py ../testdata/trumpet_video1_sheet.webp ../testdata/trumpet_video1.mp4`. Done: the pass/fail lines and any differences from Mac posted on LLD-4 comment 01a128f9
- [x] Judge the extra fault-video flags. Pull origin/main (78c7977+). Download: `backend/.venv/Scripts/python backend/scripts/fetch_youtube.py --list testdata/youtube/fault_candidates.csv`. The run raised 65 flags matching no key (testdata/youtube/fault_flags.csv vs fault_keys.csv; slouching 19, trumpet_head_down 17, bell_angle 13, shoulders_raised 12). For each, look at 2-3 frames in its window and judge REAL fault the key missed / FALSE (tracker error, camera angle, other person, not playing) / UNCLEAR. Do NOT edit backend/app/form/config.py. Done: testdata/youtube/fault_extras_judged.csv plus section "Extra flags judged (2026-10-11)" in testdata/RESULTS_form_runs.md with counts per rule and the main cause of false flags, reviewed, merged to main and pushed; 5-line summary on LLD-4 comment 01a128f9
- [ ] Re-review TASK-51 (Xavier's laptop: loosened fixed posture limits so each flags at most 3 of the 70 good videos) when it's posted on LLD-4 comment 01a128f9, as TEAM-24 promised. Done: approve or blocking points posted there

## Arnav (MacBook Air M2, 16 GB, has AWS): live AI checks
- [x] Set backend/.env: AI_ENABLED=true, BEDROCK_REGION, BEDROCK_TEXT_MODEL, BEDROCK_VISION_MODEL, AWS_PROFILE (never commit .env)
- [x] Run `python backend/scripts/live_bedrock_smoke.py`
- [x] Score referee on 2 real phone photos of sheet music: is the 0.7 confidence floor right? (good photo kept; the bad photo was rejected by homr's no_notes before the floor applied: see testdata/RESULTS_live.md)
- [x] Coach and planner on a real take (testdata/reference Ode to Joy): the output passes the checker
- [ ] Instructor chat: 3 questions about that take; each answer cites a bar or time (FAIL: see testdata/RESULTS_live.md)
- [x] Record results in testdata/RESULTS_live.md and push to main
- [x] Merge or delete branch origin/task/TASK-17

## Rikhil (MacBook Air M5, 16 GB): front end and full run
- [x] Decide whether frontend/js/results/autokey_run.js writeFeedbackAgain (5 retries on HTTP 409) is still needed now that the server does the key search; remove it if not (LLD-3 r4-C)
- [ ] After Arnav's live checks pass: one full end-to-end run with AI on (photo, confirm score, record take, feedback, plan, chat) on a laptop with AWS access
- [ ] Push fixes for every screen that breaks

## Later (waiting on Xavier)
- [ ] Phone recording over the venue Wi-Fi (wait until Xavier brings it up)
