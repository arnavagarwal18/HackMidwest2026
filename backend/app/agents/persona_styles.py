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
# Instructor only: a plan question was answered by retelling the plan's steps ("Then... Finally...") in no coach's voice
STAND_ALONE = (
    "Never retell the plan's steps in order. Every sentence stands alone: never begin one with Then, Next, Finally, "
    "Also, Lastly or First."
)
# Added after every persona text: the analysis does not measure tone, dynamics or blend, and the text may ask a coach to judge them
UNMEASURED_GUARD = (
    "Only comment on tone, dynamics or blend as things to try or listen for, never as observed faults, "
    "unless the analysis data shows them."
)

# Restated last in every step, so the persona's priorities are what the model reads just before it answers; the measured
# problem stays the same, only its framing and the exercise type differ
CONCERT_FOCUS = (
    "You are the Concert coach: frame the measured problem as a phrasing fix and pick a slow-phrase, long-tone or "
    "slurred exercise; offer dynamics only as something to try."
)
MARCHING_FOCUS = (
    "You are the Marching coach: frame the measured problem as steady pulse and consistent articulation, and pick a "
    "stationary exercise to repeat while marking time once it is clean."
)
BEGINNER_FOCUS = (
    "You are the Beginner coach: give one correction in plain words and a short exercise, such as three steady notes "
    "in a row, then rest."
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


def _persona_blocks(text: str, focus: str, plan_shape: str, guard: str = "") -> tuple[str, str, str]:
    """(coach, planner, instructor) blocks: the same text in each, that step's own additions, then the focus line."""
    return (_block(text, guard, focus), _block(text, guard, plan_shape, focus),
            _block(text, guard, OWN_INSIGHT, STAND_ALONE, focus))


CONCERT_COACH, CONCERT_PLANNER, CONCERT_INSTRUCTOR = _persona_blocks(persona_texts.CONCERT_TEXT, CONCERT_FOCUS, CONCERT_PLAN_SHAPE, UNMEASURED_GUARD)
MARCHING_COACH, MARCHING_PLANNER, MARCHING_INSTRUCTOR = _persona_blocks(
    persona_texts.MARCHING_TEXT, MARCHING_FOCUS, MARCHING_PLAN_SHAPE, UNMEASURED_GUARD
)
BEGINNER_COACH, BEGINNER_PLANNER, BEGINNER_INSTRUCTOR = _persona_blocks(persona_texts.BEGINNER_TEXT, BEGINNER_FOCUS, BEGINNER_PLAN_SHAPE, UNMEASURED_GUARD)
