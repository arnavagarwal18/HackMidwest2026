"""The Coach agent: explains a take's biggest problems and finishes by calling submit_feedback."""
from typing import Any, Callable, Literal, Optional, Union

from pydantic import BaseModel, Field
from strands import Agent, tool

from app.agents.context import CheckContext
from app.agents.holder import RunHolder
from app.agents.hooks import FEEDBACK_SUBMIT, CheckerHook
from app.agents.prompts import COACH_PROMPT
from app.agents.trace import Trace


class Claim(BaseModel):
    type: Literal["count", "timing_ms", "direction", "tempo_pct", "pitch", "form", "bar"]
    id: str = Field(description="The measurement id the claim is about")
    field: Optional[str] = Field(default=None, description="For count claims: wrong, missed, extra, late or early")
    value: Union[int, float, str, None] = Field(default=None, description="The number, direction word, pitch name or form rule claimed")
    time_s: Optional[float] = Field(default=None, description="For form claims: a time in seconds inside the flag")


class Jump(BaseModel):
    bar: Optional[int] = Field(default=None, description="A bar the sentence cites, to jump to")
    time_s: Optional[float] = Field(default=None, description="A time inside a cited form flag, to jump to")


class CoachSentence(BaseModel):
    text: str = Field(description="One sentence of at most 30 words")
    cites: list[str] = Field(description="At least one measurement id the sentence rests on")
    claims: list[Claim] = Field(default_factory=list, description="Every number, direction, pitch and form fact in the text")
    jump: Jump = Field(default_factory=Jump)


class CoachOutput(BaseModel):
    sentences: list[CoachSentence] = Field(description="1 to 6 sentences")
    problem_ids: list[str] = Field(description="1 to 3 problem ids the sentences explain")


@tool(name=FEEDBACK_SUBMIT.tool_name)
def submit_feedback(output: CoachOutput) -> dict:
    """Submit your finished feedback. The reply says accepted, or lists the sentences to fix before you submit again."""
    return {"accepted": True}  # the CheckerHook replaces this with the Checker's verdict


def build_coach_agent(model: Any, measurement_tools: list[Callable[..., str]], ctx: CheckContext, holder: RunHolder, trace: Trace) -> Agent:
    return Agent(
        model=model,
        tools=[*[tool(fn) for fn in measurement_tools], submit_feedback],
        system_prompt=COACH_PROMPT,
        hooks=[CheckerHook(FEEDBACK_SUBMIT, ctx, holder, trace)],
        callback_handler=None,
    )
