"""The CheckerHook: runs the Checker on what an agent submits and gives the agent the verdict as the tool result."""
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from strands.hooks import (
    AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry,
)

from app.agents.chat_checker import check_reply
from app.agents.checker import check_feedback, check_plan
from app.agents.context import CheckContext
from app.agents.holder import ReplyHolder, RunHolder
from app.agents.plan_rules import EXERCISE_COUNT
from app.agents.trace import Trace

log = logging.getLogger(__name__)

MAX_TRIES = 2
TRIES_KEY = "submit_tries"


@dataclass(frozen=True)
class SubmitSpec:
    """One submit tool: how to check its output, which list holds the droppable items, and where an accepted output goes."""

    tool_name: str
    items_key: str
    item_name: str  # what the agent calls one item: the key that names the failing item in a rejection
    check: Callable[[Any, CheckContext], dict]
    note_check: Callable[[Any, int, dict], None]  # called with the holder
    accept: Callable[[Any, dict, list[dict]], None]  # called with the holder
    min_items: int = 1  # fewer items than this left after dropping is a refusal, not an acceptance
    input_key: Optional[str] = "output"  # the tool argument holding the output; None when the arguments are the output


FEEDBACK_SUBMIT = SubmitSpec("submit_feedback", "sentences", "sentence", check_feedback,
                             RunHolder.note_feedback_check, RunHolder.accept_feedback)
PLAN_SUBMIT = SubmitSpec("submit_plan", "exercises", "exercise", check_plan,
                         RunHolder.note_plan_check, RunHolder.accept_plan, min_items=EXERCISE_COUNT[0])
CHAT_SUBMIT = SubmitSpec("submit_reply", "sentences", "sentence", check_reply,
                         ReplyHolder.note_check, ReplyHolder.accept, input_key=None)


def _result_content(event: AfterToolCallEvent, verdict: dict) -> dict:
    return {"toolUseId": event.tool_use["toolUseId"], "status": "success", "content": [{"json": verdict}]}


def _stop_agent(event: AfterToolCallEvent) -> None:
    """Make the agent finish after this tool batch instead of asking the model for another turn."""
    request_state = event.invocation_state.get("request_state")
    if isinstance(request_state, dict):
        request_state["stop_event_loop"] = True


class CheckerHook(HookProvider):
    """Replaces a submit tool's result with { accepted: true } or { accepted: false, try, problems }.

    A rejected first try lets the agent fix its output. On the second try, items that still fail are dropped
    and the rest accepted ({ accepted: true, dropped: n }); output that can't be repaired by dropping
    (a bad problem list, a malformed submission, every item failing) is refused for good and nothing is stored.
    """

    def __init__(self, spec: SubmitSpec, ctx: CheckContext, holder: RunHolder, trace: Optional[Trace] = None) -> None:
        self.spec, self.ctx, self.holder, self.trace = spec, ctx, holder, trace

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.after_tool_call)

    def after_tool_call(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] != self.spec.tool_name:
            return
        tries = (event.agent.state.get(TRIES_KEY) or 0) + 1
        event.agent.state.set(TRIES_KEY, tries)
        verdict, finished = self._judge(event, tries)
        event.result = _result_content(event, verdict)
        if finished:
            _stop_agent(event)

    def _judge(self, event: AfterToolCallEvent, tries: int) -> tuple[dict, bool]:
        """The verdict the agent sees, and whether the agent is done."""
        if event.result.get("status") == "error":
            output, result = None, self._malformed(event)
        else:
            tool_input = event.tool_use.get("input") or {}
            output = tool_input if self.spec.input_key is None else tool_input.get(self.spec.input_key)
            result = self.spec.check(output, self.ctx)
        self.spec.note_check(self.holder, tries, result)
        if result["ok"]:
            self._emit("check_pass", f"try {tries}: {result['claims_checked']} claims checked")
            self.spec.accept(self.holder, output, [])
            return {"accepted": True}, True
        problems = result["problems"]
        self._emit("check_fail", f"try {tries}: {len(problems)} problems, first: {problems[0]['reason']}")
        if tries < MAX_TRIES:
            return {"accepted": False, "try": tries, "problems": [self._problem_view(p) for p in problems]}, False
        dropped = self._drop_failing(output, problems)
        if dropped is None:
            log.warning("%s refused on try %s: %s", self.spec.tool_name, tries, problems[0]["reason"])
            return {"accepted": False, "try": tries, "final": True, "problems": [self._problem_view(p) for p in problems]}, True
        return {"accepted": True, "dropped": len(dropped)}, True

    def _problem_view(self, problem: dict) -> dict:
        return {self.spec.item_name: problem["index"], "claim": problem["claim"], "reason": problem["reason"]}

    def _malformed(self, event: AfterToolCallEvent) -> dict:
        detail = " ".join(c.get("text", "") for c in event.result.get("content", []) if isinstance(c, dict)).strip()
        reason = f"bad submission: {detail or 'the input did not match the schema'}"
        return {"ok": False, "problems": [{"index": None, "claim": None, "reason": reason}], "claims_checked": 0, "claims_failed": 0}

    def _drop_failing(self, output: Any, problems: list[dict]) -> Optional[list[dict]]:
        """Accept `output` without the items that fail and return them as [{ text, reasons }]; None when dropping can't fix it, which includes nothing being left."""
        items = output.get(self.spec.items_key) if isinstance(output, dict) else None
        if not isinstance(items, list) or any(not isinstance(p["index"], int) or p["index"] >= len(items) for p in problems):
            return None
        reasons: dict[int, list[str]] = {}
        for problem in problems:
            reasons.setdefault(problem["index"], []).append(problem["reason"])
        kept = [item for i, item in enumerate(items) if i not in reasons]
        if len(kept) < self.spec.min_items:
            return None
        dropped = [{"text": _item_text(items[i]), "reasons": reasons[i]} for i in sorted(reasons)]
        self.spec.accept(self.holder, {**output, self.spec.items_key: kept}, dropped)
        self._emit("check_fail", f"dropped {len(dropped)} items after try {MAX_TRIES}")
        return dropped

    def _emit(self, event: str, detail: str) -> None:
        """The seam where the trace learns what the Checker decided."""
        if self.trace is not None:
            self.trace.add("checker", event, self.spec.tool_name, detail)


def _item_text(item: Any) -> str:
    return item["text"] if isinstance(item, dict) and isinstance(item.get("text"), str) else json.dumps(item, default=str)[:200]


def _content_text(content: Any) -> str:
    """The readable part of a message's or a tool result's content blocks: text, tool calls and tool results."""
    parts = []
    for block in content if isinstance(content, list) else []:
        if not isinstance(block, dict):
            continue
        if "text" in block:
            parts.append(block["text"])
        elif "toolUse" in block:
            parts.append(f"call {block['toolUse']['name']}({json.dumps(block['toolUse'].get('input'), default=str)})")
        elif "toolResult" in block:
            parts.append(f"result: {_content_text(block['toolResult'].get('content'))}")
        elif "json" in block:
            parts.append(json.dumps(block["json"], default=str))
    return " ".join(parts)


class TraceHook(HookProvider):
    """Records every model call and tool call of one agent in the run's Trace, with the agent's name.

    Register it before the CheckerHook: Strands runs after-events in reverse order, so the Checker's
    check_pass / check_fail come first and the submit tool's tool_end shows the verdict the agent saw.
    """

    def __init__(self, trace: Trace, agent_name: str) -> None:
        self.trace, self.agent_name = trace, agent_name
        self._model_started: Optional[float] = None
        self._tools_started: dict[str, float] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeModelCallEvent, self.before_model_call)
        registry.add_callback(AfterModelCallEvent, self.after_model_call)
        registry.add_callback(BeforeToolCallEvent, self.before_tool_call)
        registry.add_callback(AfterToolCallEvent, self.after_tool_call)

    def before_model_call(self, event: BeforeModelCallEvent) -> None:
        self._model_started = time.monotonic()
        messages = event.agent.messages
        self._add("model_start", "model", _content_text(messages[-1]["content"]) if messages else "")

    def after_model_call(self, event: AfterModelCallEvent) -> None:
        duration_ms = _since_ms(self._model_started)
        if event.exception is not None:
            self._add("model_error", "model", f"{type(event.exception).__name__}: {event.exception}", duration_ms)
            return
        response = event.stop_response
        detail = f"{response.stop_reason}: {_content_text(response.message['content'])}" if response else ""
        self._add("model_end", "model", detail, duration_ms)

    def before_tool_call(self, event: BeforeToolCallEvent) -> None:
        self._tools_started[event.tool_use["toolUseId"]] = time.monotonic()
        self._add("tool_start", event.tool_use["name"], json.dumps(event.tool_use.get("input"), default=str))

    def after_tool_call(self, event: AfterToolCallEvent) -> None:
        duration_ms = _since_ms(self._tools_started.pop(event.tool_use["toolUseId"], None))
        failed = event.exception is not None or event.result.get("status") == "error"
        detail = _content_text(event.result.get("content"))
        if event.exception is not None:
            detail = f"{type(event.exception).__name__}: {event.exception}"
        self._add("tool_error" if failed else "tool_end", event.tool_use["name"], detail, duration_ms)

    def _add(self, event: str, name: str, detail: str, duration_ms: int = 0) -> None:
        self.trace.add(self.agent_name, event, name, detail, duration_ms)


def _since_ms(started: Optional[float]) -> int:
    return round((time.monotonic() - started) * 1000) if started is not None else 0
