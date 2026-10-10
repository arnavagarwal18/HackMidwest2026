"""The Planner agent: turns a take's problems into 2 to 4 practice exercises and finishes by calling submit_plan."""
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field
from strands import Agent, tool

from app.agents.coach import Claim
from app.agents.context import CheckContext
from app.agents.holder import RunHolder
from app.agents.hooks import PLAN_SUBMIT, CheckerHook, TraceHook
from app.agents.prompts import PLANNER_PROMPT
from app.agents.trace import Trace

PLANNER_TOOLS = ("list_problems", "get_bar", "get_history")


class PassMark(BaseModel):
    max_errors: int = Field(description="Wrong or missed notes allowed in a passing rep: 0 or 1")
    max_mean_timing_ms: Optional[float] = Field(default=None, description="Mean timing error allowed in a passing rep, for timing problems")
    form_rule: Optional[str] = Field(default=None, description="The form rule that must stay clear, for form problems")


class PlannedExercise(BaseModel):
    title: str
    text: str = Field(description="Plain instructions of at most 40 words")
    bar_from: int
    bar_to: int
    start_bpm: float
    target_bpm: float
    step_bpm: float = Field(description="2 to 10 BPM")
    reps_to_pass: int = Field(description="1 to 5 passing reps before the next step")
    pass_mark: PassMark
    problem_ids: list[str] = Field(description="The problem ids this exercise works on")
    claims: list[Claim] = Field(default_factory=list, description="Every measured fact stated in the text")


class PlannerOutput(BaseModel):
    exercises: list[PlannedExercise] = Field(description="2 to 4 exercises")


@tool(name=PLAN_SUBMIT.tool_name)
def submit_plan(output: PlannerOutput) -> dict:
    """Submit your finished plan. The reply says accepted, or lists the exercises to fix before you submit again."""
    return {"accepted": True}  # the CheckerHook replaces this with the Checker's verdict


def build_planner_agent(model: Any, measurement_tools: dict[str, Callable[..., str]], ctx: CheckContext, holder: RunHolder, trace: Trace) -> Agent:
    return Agent(
        model=model,
        tools=[*[tool(measurement_tools[name]) for name in PLANNER_TOOLS], submit_plan],
        system_prompt=PLANNER_PROMPT,
        hooks=[TraceHook(trace, "planner"), CheckerHook(PLAN_SUBMIT, ctx, holder, trace)],
        callback_handler=None,
    )
