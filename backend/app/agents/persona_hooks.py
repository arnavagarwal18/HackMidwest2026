"""PersonaStyleHook: watches what a style persona's agents submit and traces whether it kept the persona's style rules.

It only observes. It never changes a tool result, never blocks and never asks for a retry; the CheckerHook alone decides
what is accepted. Standard has no style rules, so it gets no hook and leaves no style events.
"""
import json
import logging
import re
from typing import Any, Callable

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

from app.agents.hooks import SubmitSpec
from app.agents.personas import MAX_FIFTEEN_WORDS, NO_UNMEASURED_JUDGMENTS, Persona
from app.agents.trace import Trace

log = logging.getLogger(__name__)

MAX_WORDS_PER_SENTENCE = 15
# Judgments of qualities the app does not measure (dynamics, volume, tone, attack quality, stamina)
UNMEASURED_JUDGMENTS = (
    "too soft", "too loud", "too quiet", "too weak", "too thin", "thin tone", "weak tone", "weak attack", "sloppy attack",
    "tired", "tiring", "fatigue", "your tone was", "your volume", "your dynamics",
)
_UNMEASURED_PATTERN = re.compile(r"\b(" + "|".join(re.escape(p) for p in UNMEASURED_JUDGMENTS) + r")\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _within_sentence_limit(text: str) -> bool:
    return all(len(sentence.split()) <= MAX_WORDS_PER_SENTENCE for sentence in _SENTENCE_END.split(text.strip()))


def _free_of_unmeasured_judgments(text: str) -> bool:
    return _UNMEASURED_PATTERN.search(text) is None


STYLE_RULES: dict[str, Callable[[str], bool]] = {
    MAX_FIFTEEN_WORDS: _within_sentence_limit,
    NO_UNMEASURED_JUDGMENTS: _free_of_unmeasured_judgments,
}


def _submitted_texts(spec: SubmitSpec, tool_input: Any) -> list[str]:
    """The text of each item (sentence or exercise) in a submission, in order; '' for an item without text."""
    output = tool_input if spec.input_key is None else (tool_input or {}).get(spec.input_key)
    items = output.get(spec.items_key) if isinstance(output, dict) else None
    return [item["text"] if isinstance(item, dict) and isinstance(item.get("text"), str) else "" for item in items or []]


def _was_accepted(event: AfterToolCallEvent) -> bool:
    for block in event.result.get("content", []):
        verdict = block.get("json") if isinstance(block, dict) else None
        if isinstance(verdict, dict):
            return verdict.get("accepted") is True
    return False


class PersonaStyleHook(HookProvider):
    """After each accepted submission, traces style_pass, or a style_fail {agent, rule, index} for every item that breaks a rule.

    Register it after the TraceHook and before the CheckerHook: Strands runs after-events in reverse order, so the
    Checker's verdict is already on the result when this runs.
    """

    def __init__(self, persona: Persona, spec: SubmitSpec, trace: Trace, agent_name: str) -> None:
        self.persona, self.spec, self.trace, self.agent_name = persona, spec, trace, agent_name
        self.rules = [(rule_id, STYLE_RULES[rule_id]) for rule_id in persona.style_rules]

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self.after_tool_call)

    def after_tool_call(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] != self.spec.tool_name or not _was_accepted(event):
            return
        try:
            failures = [(rule_id, index) for index, text in enumerate(_submitted_texts(self.spec, event.tool_use.get("input")))
                        for rule_id, passes in self.rules if not passes(text)]
        except Exception:  # observe-only: a bug here must never disturb the agent, but it is logged
            log.exception("The %s style check for the %s could not run", self.persona.id, self.agent_name)
            self.trace.add(self.agent_name, "style_error", self.persona.id, "the style check could not run")
            return
        for rule_id, index in failures:
            detail = json.dumps({"agent": self.agent_name, "rule": rule_id, "index": index})
            self.trace.add(self.agent_name, "style_fail", rule_id, detail)
        if not failures:
            self.trace.add(self.agent_name, "style_pass", self.persona.id, json.dumps({"agent": self.agent_name}))


def style_hooks(persona: Persona, spec: SubmitSpec, trace: Trace, agent_name: str) -> list[HookProvider]:
    """The hooks to register next to the CheckerHook: none for a persona without style rules."""
    return [PersonaStyleHook(persona, spec, trace, agent_name)] if persona.style_rules else []
