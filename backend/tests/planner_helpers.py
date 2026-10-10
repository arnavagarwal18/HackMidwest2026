"""Valid and invalid Planner output for the tests, and a way to run a Planner on the fixture take."""
from app.agents.holder import RunHolder
from app.agents.planner import build_planner_agent
from app.agents.tools import make_tools
from app.agents.trace import Trace
from tests.fake_model import ScriptedModel, tool_turn

# In a feedback run the take has no earlier takes, so the start ceiling is 70% of the target + 2 BPM.
BAR_3 = {
    "title": "Fix bar 3 timing",
    "text": "Play bar 3 at 50 BPM, up 4 BPM per step to 70 BPM, 3 clean reps.",
    "bar_from": 3, "bar_to": 3, "start_bpm": 50, "target_bpm": 70, "step_bpm": 4, "reps_to_pass": 3,
    "pass_mark": {"max_errors": 0, "max_mean_timing_ms": 50, "form_rule": None},
    "problem_ids": ["p:t1:1"], "claims": [],
}
WHOLE_RANGE = {
    "title": "Put it together",
    "text": "Play bars 1 to 4 from 56 BPM to 80 BPM in steps of 5, 2 clean reps.",
    "bar_from": 1, "bar_to": 4, "start_bpm": 56, "target_bpm": 80, "step_bpm": 5, "reps_to_pass": 2,
    "pass_mark": {"max_errors": 1, "max_mean_timing_ms": None, "form_rule": None},
    "problem_ids": ["p:t1:0"], "claims": [],
}
TOO_FAST = {**BAR_3, "start_bpm": 66, "text": "Play bar 3 at 66 BPM, up 4 BPM per step to 70 BPM, 3 clean reps."}


def submit_plan(*exercises):
    return tool_turn("submit_plan", {"output": {"exercises": list(exercises)}})


def run_planner(fixture_data, check_ctx, script):
    model, holder, trace = ScriptedModel(script), RunHolder(), Trace()
    tools = make_tools(fixture_data["session_id"], fixture_data["take_id"], get_diagnosis=lambda s, t: fixture_data["diagnosis"],
                       get_form=lambda s, t: fixture_data["form"], get_earlier_takes=lambda s, t: fixture_data["history"])
    agent = build_planner_agent(model, tools, check_ctx, holder, trace)
    agent("Plan take t1.")
    return agent, model, holder, trace
