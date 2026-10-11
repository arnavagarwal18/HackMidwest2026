"""The drill tools a style persona's Planner can call. Plain code: each returns one exercise template for the bars it is given.

A template is already inside the Checker's plan limits (step 2-10 BPM, 1-5 reps, max_errors 0-2). The Planner still
turns it into a full exercise and submits it through submit_plan, so the plan rules apply unchanged.
"""
import logging
from typing import Any, Callable

from strands import tool

from app.agents.personas import BEGINNER, CONCERT, MARCHING, Persona

log = logging.getLogger(__name__)

BAD_BARS_MESSAGE = "bar_from and bar_to must be whole bar numbers of 1 or more, with bar_from at most bar_to"
TWO_BARS = 2


def _bars_text(bar_from: int, bar_to: int) -> str:
    return f"bar {bar_from}" if bar_from == bar_to else f"bars {bar_from} to {bar_to}"


def _valid_bars(bar_from: Any, bar_to: Any) -> bool:
    whole = all(isinstance(bar, int) and not isinstance(bar, bool) for bar in (bar_from, bar_to))
    return whole and 1 <= bar_from <= bar_to


def _template(persona: Persona, drill: str, bar_from: int, bar_to: int, whole_range: bool, title: str, how_to: str) -> dict:
    """One exercise template. How-to text names only the exercise's own bars, step and reps, so it needs no claims."""
    bias = persona.plan_bias
    return {
        "title": title.format(bars=_bars_text(bar_from, bar_to)),
        "text": how_to.format(bars=_bars_text(bar_from, bar_to), reps=bias.reps_to_pass, step=bias.step_bpm),
        "bar_from": bar_from, "bar_to": bar_to,
        "tempo": {"kind": persona.tempo.kind, "value": persona.tempo.value},
        "step_bpm": bias.step_bpm, "reps_to_pass": bias.reps_to_pass,
        "max_errors": bias.max_errors_whole_range if whole_range else bias.max_errors_isolated,
        "drill": drill,
    }


def _drill(persona: Persona, drill: str, bar_from: Any, bar_to: Any, whole_range: bool, title: str, how_to: str,
           bars_to: Callable[[int, int], int] = lambda start, end: end) -> dict:
    if not _valid_bars(bar_from, bar_to):
        log.warning("%s called with bars %r to %r", drill, bar_from, bar_to)
        return {"error": BAD_BARS_MESSAGE}
    return _template(persona, drill, bar_from, bars_to(bar_from, bar_to), whole_range, title, how_to)


@tool(name="long_tone_drill")
def long_tone_drill(bar_from: int, bar_to: int) -> dict:
    """Concert drill for the problem bars: long tones on the problem notes, then a clean slur. Returns one exercise template to turn into an exercise."""
    return _drill(CONCERT, "long_tone_drill", bar_from, bar_to, False, "Long tones on {bars}",
                  "Hold each problem note in {bars} as a long tone, then slur cleanly to the next note. "
                  "Pass {reps} times in a row, then add {step} BPM.")


@tool(name="stamina_set")
def stamina_set(bar_from: int, bar_to: int) -> dict:
    """Marching drill over the whole range, as a stamina set: mark time with your feet to the metronome. Returns one exercise template to turn into an exercise."""
    return _drill(MARCHING, "stamina_set", bar_from, bar_to, True, "Stamina set: {bars}",
                  "Mark time with your feet to the metronome and play {bars} with full breaths and firm tongued attacks. "
                  "Pass {reps} times in a row, then add {step} BPM.")


@tool(name="two_bar_drill")
def two_bar_drill(bar_from: int, bar_to: int) -> dict:
    """Beginner drill on two bars at most, starting at bar_from: say the note names first, rest between tries. Returns one exercise template to turn into an exercise."""
    return _drill(BEGINNER, "two_bar_drill", bar_from, bar_to, False, "Two-bar practice: {bars}",
                  "Say the note names of {bars} first, then play them at an easy tempo and rest between tries. "
                  "Pass {reps} times, then add {step} BPM.",
                  bars_to=lambda start, end: min(end, start + TWO_BARS - 1))


DRILL_TOOLS = {fn.tool_name: fn for fn in (long_tone_drill, stamina_set, two_bar_drill)}


def drill_tools_for(persona: Persona) -> list:
    """The drill tools to load into this persona's Planner: its own one, or none (Standard)."""
    return [DRILL_TOOLS[persona.drill_tool]] if persona.drill_tool else []
