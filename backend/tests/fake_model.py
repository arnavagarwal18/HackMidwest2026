"""A scripted Strands model for the agent tests: each model call plays the next turn of the script."""
import asyncio
import json
import time
from typing import Any, AsyncGenerator

from strands.models import Model


def tool_turn(name: str, tool_input: dict, tool_use_id: str = "tu") -> dict:
    return {"tool": (name, tool_input, tool_use_id)}


def tools_turn(*calls: tuple[str, dict]) -> dict:
    """One reply that calls several tools, which Strands runs at the same time."""
    return {"tools": [(name, tool_input, f"tu{i}") for i, (name, tool_input) in enumerate(calls)]}


def slow(turn: dict, seconds: float) -> dict:
    """The same turn, played after the model has taken `seconds` to answer."""
    return {**turn, "delay": seconds}


def sleep_turn(seconds: float) -> dict:
    return {"sleep": seconds}


def text_turn(text: str = "done") -> dict:
    return {"text": text}


class ScriptedModel(Model):
    """Plays `script` in order across every agent that shares it; an Exception in the script is raised instead,
    and a sleep turn waits (for timeout tests).

    Running past the end of the script fails the test, so an agent that doesn't stop when it should is caught.
    """

    def __init__(self, script: list) -> None:
        self.script, self.calls = list(script), 0
        self.call_times: list[float] = []  # time.monotonic() at each model call
        self.tool_choices: list = []  # the tool_choice each model call was given

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]:
        self.calls += 1
        self.call_times.append(time.monotonic())
        self.tool_choices.append(kwargs.get("tool_choice"))
        assert self.script, f"model called a {self.calls}th time with nothing left in the script"
        turn = self.script.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if "sleep" in turn:
            await asyncio.sleep(turn["sleep"])
            return
        await asyncio.sleep(turn.get("delay", 0))
        yield {"messageStart": {"role": "assistant"}}
        calls = turn.get("tools") or ([turn["tool"]] if "tool" in turn else [])
        if calls:
            for name, tool_input, tool_use_id in calls:
                yield {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": f"{tool_use_id}{self.calls}"}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}}
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": turn["text"]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}


class RoutedModel(Model):
    """Gives each agent its own script, chosen by the agent's system prompt, so agents running at the same time
    don't have to agree on the order of their model calls."""

    def __init__(self, scripts: dict[str, list]) -> None:
        self.by_prompt = {prompt: ScriptedModel(script) for prompt, script in scripts.items()}

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]:
        async for event in self.by_prompt[system_prompt].stream(messages, tool_specs, system_prompt, **kwargs):
            yield event
