"""Ends the Orchestrator's run once a sub-agent failed on credentials."""
from typing import Any

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

from app.agents.credentials import first_credential_error
from app.agents.holder import RunHolder
from app.agents.hooks import stop_agent


class StopOnCredentialErrorHook(HookProvider):
    """Makes the Orchestrator finish once the Coach or Planner failed on credentials, instead of asking a model that will fail too."""

    def __init__(self, holder: RunHolder) -> None:
        self.holder = holder

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.after_tool_call)

    def after_tool_call(self, event: AfterToolCallEvent) -> None:
        if first_credential_error([*self.holder.errors, *self.holder.planner_errors]) is not None:
            stop_agent(event)
