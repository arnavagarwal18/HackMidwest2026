---
urgency: ride-along
component: backend/agents
audience: operators
---
Adds `python -m app.agents.live_check` (run from `backend/`): it runs the real Orchestrator, Coach, Planner and Checker once on the test trumpet take, prints each stage's time, and saves the trace to `backend/app/agents/samples/live_trace.json` (change it with `--trace-out`). On a Bedrock failure such as throttling it prints one line, exits 1 and does not retry.
