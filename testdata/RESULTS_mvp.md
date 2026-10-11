# MVP integration run (TASK-53, Xavier's Windows laptop, AI_ENABLED=false throughout, no Bedrock calls)

Main commit tested: a007bf4 (origin/main at `git fetch origin` on 2026-10-11) plus one test fix (below).

## Branches not merged into origin/main
Nothing merged. Nothing was finished work missing from main.
- origin/task/TASK-10 (calebnwaite, 1 ahead): skipped on instruction; its owner dealt with it (a WIP note commit, no code).
- origin/task/TASK-17 (arnavagarwal18, 1 ahead): skipped on instruction; unfinished Gemini switch.
- origin/task/TASK-45 (Jfranks19, 2 ahead, 2026-10-10): skipped, superseded. Its fixed trumpet limits and the elbows_wide/bell_angle rules are already on main (69c356a, d7b6ef1), and main has since loosened neck_ratio and elbows_wide (TASK-51, e98e791). Merging would put the old limits back (`git diff` on config.py shows TRUMPET_NECK_RATIO_MIN 0.15 -> 0.30 and ELBOWS_WIDE 1.3 -> 1.0). TODO.md already ticks "Merge or delete branch origin/task/TASK-45". Its RESULTS_form_runs.md section is not needed either.
No remote branch was deleted.

## Test run
`backend/.venv/Scripts/python -m pytest backend/tests -q` from the repo root:
- First run on a007bf4: 1341 passed, 3 failed, 13 skipped (441 s).
- After the fix: 1342 passed, 0 failed, 15 skipped (406 s). Exit 0.
- Skips: the 13 that were already skipped (not individually examined this run), plus 2 new environment skips: the Ctrl-C and SIGTERM cases of `test_interrupting_the_runner_stops_the_running_child`, which Windows cannot run (`send_signal` cannot deliver SIGINT/SIGTERM to a child).

## End to end (real photo trumpet_video1_sheet.webp + take trumpet_video1.mp4)
`scripts/e2e_real.py` exit 0; all steps below passed with AI off (feedback, plan and chat in fallback mode, reason "disabled").
- create session 201, upload photo 202: pass
- scan: pass (20 s, 16 bars, no doubtful bars; warning "couldn't double-check this scan" as expected with AI off)
- confirm score: pass (16 bars, 90 BPM, 4/4)
- upload take 202, take analysis: pass (32 s; 44 notes ok, 8 extras, 9 problems; played 65.6 BPM vs goal 90)
- form analysis: pass (status done; no flags raised on this clip)
- feedback: pass (mode fallback; tier 1 items for bars 7-8, 1, 5-7)
- plan: pass (ex1 bars 7-8 at 62 BPM, ex2 bar 1); GET exercise ex1 returns its state, GET progress 200
- chat (checked by hand against the same session): POST returned a fallback reply quoting the measured tier 1 items; GET returned 2 turns
- GET / 200; all 105 JS/CSS files under frontend/ (every file in js/ and css/, index.html's imports, the dynamically loaded screens) returned 200, none missing.

Port note: another process on this laptop (python.exe, PID 15204, `uvicorn app.main:app --app-dir . --port 8000`, bound to 127.0.0.1:8000) already held port 8000 and serves a different checkout, so requests to localhost:8000 never reached this branch's server. This run used port 8001 (`--port 8001`, `--server http://127.0.0.1:8001`); that process was left alone. My server was stopped at the end.

## Fixes
- backend/tests/test_batch_run.py: 3 failures were POSIX-only test code, not app bugs (batch_run.py already kills the child on Windows with `process.kill()`). `os.kill(pid, 0)` raises OSError on Windows (and would kill a live process), so a `process_exists` helper now does the check (`OpenProcess`/`GetExitCodeProcess` on Windows, `os.kill` on POSIX); the timeout test now passes on Windows. The Ctrl-C/SIGTERM tests are skipped on Windows. No app code changed.

## Still unproven
- Live AI chat on Haiku (Arnav's item): chat here ran only in fallback mode.
- Rikhil's AI-on run on a Mac.
- The two skipped interrupt tests were not run on Windows; they still need a POSIX run to confirm Ctrl-C/SIGTERM stop the child.
