"""A scripted Strands model for the agent tests: each model call plays the next turn of the script."""
import asyncio
import json
from typing import Any, AsyncGenerator

from strands.models import Model


def tool_turn(name: str, tool_input: dict, tool_use_id: str = "tu") -> dict:
    return {"tool": (name, tool_input, tool_use_id)}


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

    def update_config(self, **model_config: Any) -> None:
        pass

    def get_config(self) -> Any:
        return {}

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):
        raise NotImplementedError
        yield

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]:
        self.calls += 1
        assert self.script, f"model called a {self.calls}th time with nothing left in the script"
        turn = self.script.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if "sleep" in turn:
            await asyncio.sleep(turn["sleep"])
            return
        yield {"messageStart": {"role": "assistant"}}
        if "tool" in turn:
            name, tool_input, tool_use_id = turn["tool"]
            yield {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": f"{tool_use_id}{self.calls}"}}}}
            yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(tool_input)}}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockDelta": {"delta": {"text": turn["text"]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}
