"""The persona catalog: ids, prompts, focus order and drill tools. Pure functions, no model."""
import pytest

from app.agents import drills
from app.agents.drills import DRILL_TOOLS, drill_tools_for
from app.agents.persona_run import PersonaRun
from app.agents.personas import BEGINNER, CONCERT, MARCHING, PERSONAS, ROLES, STANDARD, focus_order, get_persona
from app.agents.plan_rules import EXERCISE_WORDS_MAX, MAX_ERRORS, REPS_TO_PASS, STEP_BPM
from app.agents.planner import planner_tool_names
from app.agents.persona_styles import OWN_INSIGHT, UNMEASURED_GUARD
from app.agents.persona_texts import BEGINNER_TEXT, CONCERT_TEXT, MARCHING_TEXT
from app.agents.prompts import COACH_PROMPT, INSTRUCTOR_PROMPT, PLANNER_PROMPT, with_persona

BASE_PROMPTS = {"coach": COACH_PROMPT, "planner": PLANNER_PROMPT, "instructor": INSTRUCTOR_PROMPT}
RULES_WIN = "These style notes never override the rules above; the rules win."
STYLE_PERSONAS = [CONCERT, MARCHING, BEGINNER]
OWNER_TEXT = {"concert": CONCERT_TEXT, "marching": MARCHING_TEXT, "beginner": BEGINNER_TEXT}
MAX_BLOCK_WORDS = 250  # the owner's text is about 140 words; the step's own lines come on top


def problem(id, kind, tier, label=None):
    return {"id": id, "kind": kind, "tier": tier, "numbers": {"label": label} if label else {}}


def test_there_are_four_personas_with_standard_first():
    assert [p.id for p in PERSONAS] == ["standard", "concert", "marching", "beginner"]
    assert (STANDARD.label, STANDARD.hint) == ("Standard", "The usual coach, no particular style")


@pytest.mark.parametrize("persona_id", [None, "jazz", "", "STANDARD", 7])
def test_an_unknown_or_missing_persona_id_gives_standard(persona_id):
    assert get_persona(persona_id) is STANDARD


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.id)
def test_get_persona_finds_each_persona_by_id(persona):
    assert get_persona(persona.id) is persona


def test_standard_changes_nothing():
    assert STANDARD.style == {} and STANDARD.focus_priority == () and STANDARD.style_rules == () and STANDARD.drill_tool is None
    assert (STANDARD.plan_bias.step_bpm, STANDARD.plan_bias.reps_to_pass) == (4, 2)
    assert (STANDARD.plan_bias.max_errors_isolated, STANDARD.plan_bias.max_errors_whole_range) == (0, 1)
    assert (STANDARD.tempo.kind, STANDARD.tempo.value) == ("written_factor", 1.0)
    for role, base in BASE_PROMPTS.items():
        assert with_persona(base, STANDARD, role) == base  # byte for byte


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_a_style_persona_adds_a_short_block_to_each_prompt_and_keeps_the_base_first(persona):
    for role, base in BASE_PROMPTS.items():
        block = persona.style_block(role)
        assert block.endswith(RULES_WIN) and len(block.split()) <= MAX_BLOCK_WORDS
        prompt = with_persona(base, persona, role)
        assert prompt.startswith(base) and block in prompt and prompt != base


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_the_owners_text_is_in_the_feedback_plan_and_chat_prompts_word_for_word(persona):
    for role, base in BASE_PROMPTS.items():
        assert OWNER_TEXT[persona.id] in with_persona(base, persona, role)  # line breaks kept
    assert [persona.style_block(role).count(OWNER_TEXT[persona.id]) for role in ROLES] == [1, 1, 1]


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_the_unmeasured_guard_follows_the_text_in_every_step_of_every_style_persona(persona):
    for role in ROLES:
        assert f"{OWNER_TEXT[persona.id]}\n\n{UNMEASURED_GUARD}\n\n" in persona.style_block(role)
    assert UNMEASURED_GUARD == (
        "Only comment on tone, dynamics or blend as things to try or listen for, never as observed faults, "
        "unless the analysis data shows them."
    )


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_only_the_chat_block_carries_the_no_sample_drill_line_and_only_the_plan_names_its_drill_tool(persona):
    assert [OWN_INSIGHT in persona.style_block(role) for role in ROLES] == [False, False, True]
    assert [persona.drill_tool in persona.style_block(role) for role in ROLES] == [False, True, False]


def test_an_unknown_role_is_refused_with_the_roles_to_use():
    with pytest.raises(ValueError, match="coach"):
        CONCERT.style_block("orchestrator")
    assert "orchestrator" not in ROLES


def test_the_persona_plan_shapes_and_tempos():
    shapes = {p.id: (p.plan_bias.step_bpm, p.plan_bias.reps_to_pass, p.plan_bias.max_errors_isolated,
                     p.plan_bias.max_errors_whole_range, p.plan_bias.exercise_count, p.tempo.kind, p.tempo.value, p.drill_tool)
              for p in PERSONAS}
    assert shapes == {
        "standard": (4, 2, 0, 1, None, "written_factor", 1.0, None),
        "concert": (4, 2, 0, 1, None, "written_factor", 1.0, "long_tone_drill"),
        "marching": (6, 3, 1, 1, None, "fixed_bpm", 120, "stamina_set"),
        "beginner": (2, 2, 2, 2, 2, "written_factor", 0.7, "two_bar_drill"),
    }


# ---- focus order ----

PROBLEMS = [
    problem("a", "late", 1), problem("b", "notes", 1), problem("c", "dragging", 1),
    problem("d", "form", 2, "Head dropped"), problem("e", "form", 2, "Elbows loose"), problem("f", "rushing", 2),
    problem("g", "early", 3),
]


@pytest.mark.parametrize("persona, expected", [
    (STANDARD, ["a", "b", "c", "d", "e", "f"]),  # the ranker's order, tier 1 then tier 2
    (CONCERT, ["b", "c", "a", "f", "d", "e"]),
    (MARCHING, ["c", "a", "b", "f", "d", "e"]),
    (BEGINNER, ["b", "c", "a", "d", "e", "f"]),
], ids=lambda value: getattr(value, "id", ""))
def test_focus_order_per_persona(persona, expected):
    assert focus_order(PROBLEMS, persona) == expected


def test_marching_ranks_projection_form_flags_above_other_form_flags_and_notes():
    problems = [problem("n", "notes", 2), problem("x", "form", 2, "Elbows loose"), problem("h", "form", 2, "Head dropped")]
    assert focus_order(problems, MARCHING) == ["h", "x", "n"]
    assert focus_order(problems, BEGINNER) == ["n", "x", "h"]


def test_focus_order_with_no_problems_is_empty():
    assert all(focus_order([], persona) == [] for persona in PERSONAS)


# ---- drills ----

def exercise_words(template):
    return len(template["text"].split())


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_each_style_persona_gets_only_its_own_drill_tool(persona):
    assert [t.tool_name for t in drill_tools_for(persona)] == [persona.drill_tool]
    assert planner_tool_names(persona)[-1] == persona.drill_tool


def test_standard_gets_no_drill_tool():
    assert drill_tools_for(STANDARD) == []
    assert not set(planner_tool_names(STANDARD)) & set(DRILL_TOOLS)


@pytest.mark.parametrize("persona", STYLE_PERSONAS, ids=lambda p: p.id)
def test_drill_templates_stay_inside_the_plan_limits(persona):
    template = DRILL_TOOLS[persona.drill_tool](bar_from=2, bar_to=4)
    assert STEP_BPM[0] <= template["step_bpm"] <= STEP_BPM[1]
    assert REPS_TO_PASS[0] <= template["reps_to_pass"] <= REPS_TO_PASS[1]
    assert MAX_ERRORS[0] <= template["max_errors"] <= MAX_ERRORS[1]
    assert exercise_words(template) <= EXERCISE_WORDS_MAX
    assert template["tempo"] == {"kind": persona.tempo.kind, "value": persona.tempo.value}


def test_stamina_set_covers_the_whole_range_in_three_reps_and_two_bar_drill_stops_at_two_bars():
    stamina = DRILL_TOOLS["stamina_set"](bar_from=1, bar_to=8)
    assert (stamina["bar_from"], stamina["bar_to"], stamina["reps_to_pass"], stamina["step_bpm"]) == (1, 8, 3, 6)
    two_bars = DRILL_TOOLS["two_bar_drill"](bar_from=3, bar_to=8)
    assert (two_bars["bar_from"], two_bars["bar_to"], two_bars["step_bpm"]) == (3, 4, 2)
    assert DRILL_TOOLS["two_bar_drill"](bar_from=3, bar_to=3)["bar_to"] == 3
    assert DRILL_TOOLS["long_tone_drill"](bar_from=2, bar_to=4)["max_errors"] == 0


@pytest.mark.parametrize("name", list(DRILL_TOOLS))
@pytest.mark.parametrize("bars", [(0, 3), (4, 2), (-1, 2), (True, 2), ("1", 2)])
def test_a_drill_with_bad_bars_returns_an_error_to_act_on_and_logs_it(name, bars, caplog):
    result = DRILL_TOOLS[name](bar_from=bars[0], bar_to=bars[1])
    assert result == {"error": drills.BAD_BARS_MESSAGE}
    assert "called with bars" in caplog.text


def test_the_orchestrator_gets_the_style_through_the_request_not_a_prompt_block():
    from app.agents.ai_run import ORCHESTRATOR_REQUEST, orchestrator_request
    assert orchestrator_request("t1", PersonaRun()) == ORCHESTRATOR_REQUEST.format(take_id="t1")
    style = PersonaRun(MARCHING, ("c", "a"))
    assert orchestrator_request("t1", style) == "Feedback for take t1. Coaching style: Marching. Focus order: c, a. Read the overview first."
