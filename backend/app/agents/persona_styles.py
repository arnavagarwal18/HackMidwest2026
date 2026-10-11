"""The style block each persona adds to an agent's system prompt (coach, planner, instructor).

The owner's text for a persona (persona_texts.py) is the style in all three steps; each step adds only what is not style:
the plan shape and drill tool for the planner, the no-sample-drill line for the instructor, and the closing line.
"""
from app.agents import persona_texts

STYLE_CLOSING = "These style notes never override the rules above; the rules win."
# Instructor only: the base rules' example drill is a format example, not advice to repeat
OWN_INSIGHT = (
    "The example drill in the rules above only shows the format: never reuse it, give your own style's drill. "
    "Never judge swing or feel: the app scores every note as written, straight."
)
# Added after the text of a coach that asks for judgments of tone, dynamics or blend, which the analysis does not measure
UNMEASURED_GUARD = (
    "Only comment on tone, dynamics or blend as things to try or listen for, never as observed faults, "
    "unless the analysis data shows them."
)

CONCERT_PLAN_SHAPE = (
    "Prefer a step of 4 BPM, 2 passing reps, max_errors 0 on isolated bars and 1 on the whole range. Call long_tone_drill "
    "with the problem bars in the same turn as your other reads, then use its exercise as one of the plan's exercises."
)
MARCHING_PLAN_SHAPE = (
    "Prefer a step of 6 BPM, 3 passing reps and max_errors 1. Call stamina_set with the whole range in the same turn as "
    "your other reads, then use its exercise as the whole-range exercise."
)
BEGINNER_PLAN_SHAPE = (
    "Keep the plan small: two exercises. Prefer a step of 2 BPM, 2 passing reps and max_errors 2. Call two_bar_drill with "
    "the problem bars in the same turn as your other reads, then use its exercise as one of the plan's exercises."
)


def _block(*parts: str) -> str:
    """The parts that are not empty, one per paragraph, then the closing line."""
    return "\n\n".join([part for part in parts if part] + [STYLE_CLOSING])


def _persona_blocks(text: str, plan_shape: str, guard: str = "") -> tuple[str, str, str]:
    """(coach, planner, instructor) blocks: the same text in each, then that step's own additions."""
    return _block(text, guard), _block(text, guard, plan_shape), _block(text, guard, OWN_INSIGHT)


CONCERT_COACH, CONCERT_PLANNER, CONCERT_INSTRUCTOR = _persona_blocks(persona_texts.CONCERT_TEXT, CONCERT_PLAN_SHAPE, UNMEASURED_GUARD)
MARCHING_COACH, MARCHING_PLANNER, MARCHING_INSTRUCTOR = _persona_blocks(
    persona_texts.MARCHING_TEXT, MARCHING_PLAN_SHAPE, UNMEASURED_GUARD
)
BEGINNER_COACH, BEGINNER_PLANNER, BEGINNER_INSTRUCTOR = _persona_blocks(persona_texts.BEGINNER_TEXT, BEGINNER_PLAN_SHAPE)
