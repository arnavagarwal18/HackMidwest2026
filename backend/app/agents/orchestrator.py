"""The Orchestrator agent: reads the take overview and hands the Coach and the Planner their briefs."""
import json
import logging
from typing import Any, Awaitable, Callable

from strands import Agent, tool
from strands.tools.executors import ConcurrentToolExecutor

from app.agents.coach import build_coach_agent
from app.agents.context import CheckContext
from app.agents.holder import RunHolder
from app.agents.planner import build_planner_agent
from app.agents.prompts import ORCHESTRATOR_PROMPT
from app.agents.trace import Trace

log = logging.getLogger(__name__)


def _sub_agent_tool(name: str, description: str, run_agent: Callable[[str], Awaitable[Any]],
                    accepted: Callable[[], dict | None], errors: list[Exception], trace: Trace):
    """An async tool that runs a fresh sub-agent on the brief and returns its accepted output as JSON."""

    @tool(name=name, description=description)
    async def run(brief: str) -> str:
        trace.add("orchestrator", "tool", name, brief)
        try:
            await run_agent(brief)
        except Exception as exc:
            # Kept for run_feedback, which tells a model failure from a rejection; the Orchestrator only needs to stop waiting.
            log.exception("The %s failed", name)
            errors.append(exc)
            trace.add(name, "error", type(exc).__name__)
            return json.dumps({"error": f"the {name} could not finish"})
        output = accepted()
        return json.dumps(output) if output is not None else json.dumps({"error": f"the {name} produced no accepted output"})

    return run


def build_orchestrator(model: Any, measurement_tools: dict[str, Callable[..., str]], ctx: CheckContext, holder: RunHolder, trace: Trace) -> Agent:
    coach = _sub_agent_tool(
        "coach",
        "Run the Coach on a brief naming the take, its tier 1 problem ids, the bars, that the learner plays trumpet, and any form flags. Returns the accepted feedback as JSON.",
        lambda brief: build_coach_agent(model, list(measurement_tools.values()), ctx, holder, trace).invoke_async(brief),
        lambda: holder.feedback, holder.errors, trace)
    planner = _sub_agent_tool(
        "planner",
        "Run the Planner on a brief naming the take, its tier 1 problem ids, the bars and that the learner plays trumpet. Returns the accepted practice exercises as JSON.",
        lambda brief: build_planner_agent(model, measurement_tools, ctx, holder, trace).invoke_async(brief),
        lambda: holder.plan, holder.planner_errors, trace)
    return Agent(
        model=model,
        tools=[*[tool(fn) for fn in measurement_tools.values()], coach, planner],
        system_prompt=ORCHESTRATOR_PROMPT,
        tool_executor=ConcurrentToolExecutor(),  # the tool calls of one reply run at the same time
        callback_handler=None,
    )
