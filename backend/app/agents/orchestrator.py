"""The Orchestrator agent: reads the take overview and hands the Coach a brief."""
import json
import logging
from typing import Any, Callable

from strands import Agent, tool

from app.agents.coach import build_coach_agent
from app.agents.context import CheckContext
from app.agents.holder import RunHolder
from app.agents.prompts import ORCHESTRATOR_PROMPT
from app.agents.trace import Trace

log = logging.getLogger(__name__)


def _coach_tool(model: Any, measurement_tools: list[Callable[..., str]], ctx: CheckContext, holder: RunHolder, trace: Trace):
    @tool(name="coach")
    async def coach(brief: str) -> str:
        """Run the Coach on a brief naming the take, its tier 1 problem ids, the bars, the instrument and any form flags. Returns the accepted feedback as JSON."""
        trace.add("orchestrator", "tool", "coach", brief)
        try:
            await build_coach_agent(model, measurement_tools, ctx, holder, trace).invoke_async(brief)
        except Exception as exc:
            # Kept for run_feedback, which tells a model failure from a rejection; the Orchestrator only needs to stop waiting.
            log.exception("The Coach failed")
            holder.errors.append(exc)
            trace.add("coach", "error", type(exc).__name__)
            return json.dumps({"error": "the coach could not finish"})
        if holder.feedback is None:
            return json.dumps({"error": "the coach produced no accepted feedback"})
        return json.dumps(holder.feedback)

    return coach


def build_orchestrator(model: Any, measurement_tools: dict[str, Callable[..., str]], ctx: CheckContext, holder: RunHolder, trace: Trace) -> Agent:
    tools = list(measurement_tools.values())
    return Agent(
        model=model,
        tools=[*[tool(fn) for fn in tools], _coach_tool(model, tools, ctx, holder, trace)],
        system_prompt=ORCHESTRATOR_PROMPT,
        callback_handler=None,
    )
