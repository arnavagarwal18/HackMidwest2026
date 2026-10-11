"""The persona one feedback run or chat reply uses: read from the session once, traced, and written onto the agents."""
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.agents.personas import STANDARD, Persona, focus_order, get_persona, is_known
from app.agents.trace import Trace

log = logging.getLogger(__name__)

PERSONA_STATE_KEY = "persona"
FOCUS_ORDER_STATE_KEY = "focus_order"


@dataclass(frozen=True)
class PersonaRun:
    """The persona for a run, and the problem ids in the order it wants them explained."""

    persona: Persona = STANDARD
    focus_order: tuple[str, ...] = field(default_factory=tuple)


def resolve_persona(stored_id: str | None, trace: Trace, agent: str) -> Persona:
    """The session's persona. An id that is no longer offered gives Standard and a persona_unknown trace event."""
    if stored_id is not None and not is_known(stored_id):
        trace.add(agent, "persona_unknown", str(stored_id), json.dumps({"stored_id": stored_id}))
    return get_persona(stored_id)


def build_persona_run(stored_id: str | None, problems: list[dict], trace: Trace, agent: str = "orchestrator") -> PersonaRun:
    """The persona and focus order for a run. Never raises: odd problem data gives a Standard run (logged and traced), so the learner still gets feedback."""
    try:
        persona = resolve_persona(stored_id, trace, agent)
        return PersonaRun(persona, tuple(focus_order(problems, persona)))
    except Exception:
        log.exception("Could not build the %r persona run; using Standard with no focus order", stored_id)
        trace.add(agent, "persona_error", str(stored_id), "the persona run could not be built; Standard is used")
        return PersonaRun()


def tag_agent(agent: Any, run: PersonaRun) -> Any:
    """Write the persona and focus order into the agent's state, so hooks and traces can read them. Returns the agent."""
    agent.state.set(PERSONA_STATE_KEY, run.persona.id)
    agent.state.set(FOCUS_ORDER_STATE_KEY, list(run.focus_order))
    return agent


def trace_persona(trace: Trace, run: PersonaRun, tools: list[str]) -> None:
    """The persona trace event at the start of a feedback run: its id, focus order and the Planner's tools.

    Standard leaves no event, so a session that never picks a persona has the same trace as before personas.
    """
    if run.persona is STANDARD:
        return
    detail = json.dumps({"id": run.persona.id, "focus_order": list(run.focus_order), "tools": tools})
    trace.add("orchestrator", "persona", run.persona.id, detail)
