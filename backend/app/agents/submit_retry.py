"""Gets an agent to finish by calling its submit tool: when a model answers in plain text, ask once more and force the call."""
import logging
from typing import Any, AsyncIterable, Callable, Optional

from app.agents.hooks import MAX_TRIES, TRIES_KEY
from app.agents.trace import Trace

log = logging.getLogger(__name__)

REPROMPT = "Reply only by calling {tool_name}. Do not write plain text."


class ForcedToolModel:
    """Wraps a Strands model so every call it makes must be a call of one named tool (Bedrock's toolChoice); anything else is passed through."""

    def __init__(self, model: Any, tool_name: str) -> None:
        self._model, self._tool_name = model, tool_name

    def stream(self, *args: Any, **kwargs: Any) -> AsyncIterable[dict]:
        return self._model.stream(*args, **{**kwargs, "tool_choice": {"tool": {"name": self._tool_name}}})

    def __getattr__(self, name: str) -> Any:
        return getattr(self._model, name)


def _needs_reprompt(agent: Any, accepted: Callable[[], bool]) -> bool:
    """True when the agent stopped without an accepted submit and the Checker has not already refused its last try for good."""
    return not accepted() and (agent.state.get(TRIES_KEY) or 0) < MAX_TRIES


async def invoke_until_submitted(agent: Any, prompt: str, *, agent_name: str, tool_name: str,
                                 accepted: Callable[[], bool], trace: Optional[Trace] = None) -> None:
    """Run `agent` on `prompt`. If it ends without an accepted `tool_name` call, run it once more with the call forced.

    Nothing the model says outside the tool is used: an answer only counts once the tool's hook (the Checker) accepts it.
    Raises whatever the model raises; a second miss is only logged and traced, and the caller falls back as before.
    """
    await agent.invoke_async(prompt)
    if not _needs_reprompt(agent, accepted):
        return
    log.warning("The %s ended without calling %s; asking once more with the call forced", agent_name, tool_name)
    if trace is not None:
        trace.add(agent_name, "reminder", tool_name, "the model answered without calling the submit tool")
    unforced = agent.model
    agent.model = ForcedToolModel(unforced, tool_name)
    try:
        await agent.invoke_async(REPROMPT.format(tool_name=tool_name))
    finally:
        agent.model = unforced
    if not accepted():
        log.error("The %s still gave no accepted %s after the re-prompt", agent_name, tool_name)
