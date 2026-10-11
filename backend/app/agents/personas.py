"""Instrument personas: the coaching styles a learner can pick. Plain data and functions, no model and no storage.

Standard is the default and changes nothing: no style blocks, the ranker's problem order, no drill tool.
"""
import logging
from dataclasses import dataclass, field

from app.agents import persona_styles as styles
from app.agents.fallback import CLEAN_RUN_MAX_ERRORS, REPS_TO_PASS, STEP_BPM, WHOLE_RANGE_MAX_ERRORS
from app.diagnosis import config as diagnosis_config
from app.errors import AppError
from app.store import DEFAULT_PERSONA

log = logging.getLogger(__name__)

STANDARD_ID = DEFAULT_PERSONA
ROLES = ("coach", "planner", "instructor")
PICK_A_STYLE = "Pick a coach style from the list."
FOCUSED_TIERS = (1, 2)
UNRANKED = 99  # a problem kind the persona has no priority for goes after the ones it has

# The ranker's problem kinds, plus a form problem whose flag hurts projection (Marching ranks those above other form flags)
FORM_PROJECTION = "form_projection"
PROJECTION_LABELS = ("head dropped", "shoulders raised", "slouching", "pinned")
NOTES, FORM = diagnosis_config.PROBLEM_NOTES, diagnosis_config.PROBLEM_FORM
LATE, EARLY = diagnosis_config.TIMING_LATE, diagnosis_config.TIMING_EARLY
RUSHING, DRAGGING = diagnosis_config.DRIFT_RUSHING, diagnosis_config.DRIFT_DRAGGING

NO_UNMEASURED_JUDGMENTS = "no_unmeasured_judgments"  # style rule ids; persona_hooks.py holds the checks
MAX_FIFTEEN_WORDS = "max_15_words"


@dataclass(frozen=True)
class TempoRule:
    """How the persona's practice tempo is chosen: a factor of the written tempo, or one fixed BPM."""

    kind: str  # 'written_factor' | 'fixed_bpm'
    value: float


@dataclass(frozen=True)
class PlanBias:
    """The plan shape a persona leans toward; always inside the Checker's plan limits."""

    step_bpm: int
    reps_to_pass: int
    max_errors_isolated: int
    max_errors_whole_range: int
    exercise_count: int | None = None  # None: the Planner's own 2 to 4


@dataclass(frozen=True)
class Persona:
    id: str
    label: str
    hint: str
    voice: str
    style: dict[str, str]  # role ('coach' | 'planner' | 'instructor') -> style block; empty for Standard
    focus_priority: tuple[str, ...]  # problem kinds, most important first; empty keeps the ranker's order
    plan_bias: PlanBias
    drill_tool: str | None
    tempo: TempoRule
    style_rules: tuple[str, ...] = field(default_factory=tuple)

    def style_block(self, role: str) -> str:
        if role not in ROLES:
            raise ValueError(f"Unknown agent role '{role}'; use one of {ROLES}")
        return self.style.get(role, "")


STANDARD = Persona(
    id=STANDARD_ID, label="Standard", hint="The usual coach, no particular style", voice="warm and plain-spoken",
    style={}, focus_priority=(), plan_bias=PlanBias(STEP_BPM, REPS_TO_PASS, CLEAN_RUN_MAX_ERRORS, WHOLE_RANGE_MAX_ERRORS),
    drill_tool=None, tempo=TempoRule("written_factor", 1.0),
)
CONCERT = Persona(
    id="concert", label="Concert", hint="Band, orchestra, solos and etudes",
    voice="precise and formal, complete sentences, no slang, no exclamation marks",
    style={"coach": styles.CONCERT_COACH, "planner": styles.CONCERT_PLANNER, "instructor": styles.CONCERT_INSTRUCTOR},
    focus_priority=(NOTES, RUSHING, DRAGGING, LATE, EARLY, FORM),
    plan_bias=PlanBias(STEP_BPM, REPS_TO_PASS, CLEAN_RUN_MAX_ERRORS, WHOLE_RANGE_MAX_ERRORS),
    drill_tool="long_tone_drill", tempo=TempoRule("written_factor", 1.0),
    style_rules=(NO_UNMEASURED_JUDGMENTS,),
)
MARCHING = Persona(
    id="marching", label="Marching", hint="Marching band, pep band and field shows",
    voice="short, direct and imperative, at most 15 words a sentence",
    style={"coach": styles.MARCHING_COACH, "planner": styles.MARCHING_PLANNER, "instructor": styles.MARCHING_INSTRUCTOR},
    focus_priority=(RUSHING, DRAGGING, LATE, EARLY, FORM_PROJECTION, FORM, NOTES),
    plan_bias=PlanBias(6, 3, 1, 1),
    drill_tool="stamina_set", tempo=TempoRule("fixed_bpm", 120),
    style_rules=(MAX_FIFTEEN_WORDS, NO_UNMEASURED_JUDGMENTS),
)
BEGINNER = Persona(
    id="beginner", label="Beginner", hint="New to trumpet, any style",
    voice="warm and encouraging, plain words, one idea per sentence",
    style={"coach": styles.BEGINNER_COACH, "planner": styles.BEGINNER_PLANNER, "instructor": styles.BEGINNER_INSTRUCTOR},
    focus_priority=(NOTES, FORM, RUSHING, DRAGGING, LATE, EARLY),
    plan_bias=PlanBias(2, 2, 2, 2, exercise_count=2),
    drill_tool="two_bar_drill", tempo=TempoRule("written_factor", 0.7),
    style_rules=(NO_UNMEASURED_JUDGMENTS,),
)

PERSONAS: tuple[Persona, ...] = (STANDARD, CONCERT, MARCHING, BEGINNER)  # Standard first
_BY_ID = {persona.id: persona for persona in PERSONAS}


def is_known(persona_id: object) -> bool:
    return isinstance(persona_id, str) and persona_id in _BY_ID


def require_known(persona_id: object) -> str:
    """The id itself when it names a persona on offer; otherwise a 422 the learner can act on."""
    if not is_known(persona_id):
        log.info("Rejected persona id %r", persona_id)
        raise AppError(422, "bad_request", PICK_A_STYLE)
    return persona_id


def get_persona(persona_id: str | None) -> Persona:
    """The persona with this id; Standard for None or an id no longer offered (an old 'jazz', say)."""
    if persona_id is None:
        return STANDARD
    if not is_known(persona_id):
        log.warning("Unknown persona id %r; using Standard", persona_id)
        return STANDARD
    return _BY_ID[persona_id]


def _bucket(problem: dict) -> str:
    """The kind a persona ranks a problem by: its own, except form problems about projection."""
    kind = problem.get("kind")
    label = str((problem.get("numbers") or {}).get("label", "")).lower()
    if kind == FORM and any(word in label for word in PROJECTION_LABELS):
        return FORM_PROJECTION
    return kind


def focus_order(problems: list[dict], persona: Persona) -> list[str]:
    """Ids of the tier 1 then tier 2 problems, by the persona's kind priority and the ranker's order within a kind.

    Standard (no priority) keeps the ranker's order. A form problem the persona has no projection entry for counts as form.
    """
    chosen = [p for p in problems if p.get("tier") in FOCUSED_TIERS]
    if not persona.focus_priority:
        return [p["id"] for p in chosen]

    def rank(problem: dict) -> tuple[int, int]:
        priority = persona.focus_priority
        bucket = _bucket(problem)
        if bucket == FORM_PROJECTION and bucket not in priority:
            bucket = FORM
        return problem["tier"], priority.index(bucket) if bucket in priority else UNRANKED

    return [p["id"] for p in sorted(chosen, key=rank)]  # sorted() is stable: the ranker's order is kept within a kind
