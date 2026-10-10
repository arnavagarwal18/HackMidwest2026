"""The CheckerHook: runs the Checker on what an agent submits and gives the agent the verdict as the tool result."""
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

from app.agents.checker import check_feedback, check_plan
from app.agents.context import CheckContext
from app.agents.holder import RunHolder
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
    note_check: Callable[[RunHolder, int, dict], None]
    accept: Callable[[RunHolder, dict, list[dict]], None]
    min_items: int = 0  # fewer items than this left after dropping is a refusal, not an acceptance


FEEDBACK_SUBMIT = SubmitSpec("submit_feedback", "sentences", "sentence", check_feedback,
                             RunHolder.note_feedback_check, RunHolder.accept_feedback)
PLAN_SUBMIT = SubmitSpec("submit_plan", "exercises", "exercise", check_plan,
                         RunHolder.note_plan_check, RunHolder.accept_plan, min_items=EXERCISE_COUNT[0])


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
    (a bad problem list, a malformed submission) is refused for good and nothing is stored.
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
            output = (event.tool_use.get("input") or {}).get("output")
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
        """Accept `output` without the items that fail and return them as [{ text, reasons }]; None when dropping can't fix it."""
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
