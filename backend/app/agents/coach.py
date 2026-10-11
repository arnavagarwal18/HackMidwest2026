"""The Coach agent: explains a take's biggest problems and finishes by calling submit_feedback."""
from typing import Any, Callable, Literal, Optional, Union

from pydantic import BaseModel, Field
from strands import Agent, tool

from app.agents.context import CheckContext
from app.agents.holder import RunHolder
from app.agents.hooks import FEEDBACK_SUBMIT, CheckerHook, TraceHook
from app.agents.model import with_max_tokens
from app.agents.persona_hooks import style_hooks
from app.agents.persona_run import PersonaRun, tag_agent
from app.agents.prompts import COACH_PROMPT, with_persona
from app.agents.trace import Trace

COACH_MAX_TOKENS = 1500  # up to 6 cited sentences with their claims, as one submit_feedback call


CLAIM_VALUE_HELP = (
    "Always set it, copied from the tool result: count = the number in numbers or the bar's count; timing_ms = the timing in ms; "
    "direction = late, early, sharp, flat, rushing or dragging; tempo_pct = the drift percentage; "
    "pitch = the note the learner PLAYED (played_name), never the written note, and never for a missed note; "
    "form = the flag's rule name; bar = a bar number the item lies in"
)


class Claim(BaseModel):
    type: Literal["count", "timing_ms", "direction", "tempo_pct", "pitch", "form", "bar"]
    id: str = Field(description="The measurement id the claim is about")
    field: Optional[str] = Field(default=None, description="For count claims: wrong, missed, extra, late or early")
    value: Union[int, float, str, None] = Field(default=None, description=CLAIM_VALUE_HELP)
    time_s: Optional[float] = Field(default=None, description="For form claims (required): a time in seconds inside the flag")


class Jump(BaseModel):
    bar: Optional[int] = Field(default=None, description="A bar the sentence cites, to jump to")
    time_s: Optional[float] = Field(default=None, description="A time inside a cited form flag, to jump to")


class CoachSentence(BaseModel):
    text: str = Field(description="One sentence of at most 30 words")
    cites: list[str] = Field(description="At least one measurement id the sentence rests on")
    claims: list[Claim] = Field(default_factory=list, description="Every number, direction, pitch and form fact in the text")
    jump: Optional[Jump] = Field(default=None, description="Null when the sentence has no jump")


class CoachOutput(BaseModel):
    sentences: list[CoachSentence] = Field(description="1 to 6 sentences")
    problem_ids: list[str] = Field(description="1 to 3 problem ids the sentences explain")


@tool(name=FEEDBACK_SUBMIT.tool_name)
def submit_feedback(output: CoachOutput) -> dict:
    """Submit your finished feedback. The reply says accepted, or lists the sentences to fix before you submit again."""
    return {"accepted": True}  # the CheckerHook replaces this with the Checker's verdict


def build_coach_agent(model: Any, measurement_tools: list[Callable[..., str]], ctx: CheckContext, holder: RunHolder, trace: Trace,
                      style: PersonaRun = PersonaRun()) -> Agent:
    agent = Agent(
        model=with_max_tokens(model, COACH_MAX_TOKENS),
        tools=[*[tool(fn) for fn in measurement_tools], submit_feedback],
        system_prompt=with_persona(COACH_PROMPT, style.persona, "coach"),
        hooks=[TraceHook(trace, "coach"), *style_hooks(style.persona, FEEDBACK_SUBMIT, trace, "coach"),
               CheckerHook(FEEDBACK_SUBMIT, ctx, holder, trace)],
        callback_handler=None,
    )
    return tag_agent(agent, style)
