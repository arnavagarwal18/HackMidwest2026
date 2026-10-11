"""The Instructor agent: answers a learner's chat message about one take and finishes by calling submit_reply."""
import json
import logging
from typing import Any, Callable

from strands import Agent, tool

from app import store
from app.agents.coach import CoachSentence
from app.agents.context import CheckContext
from app.agents.holder import ReplyHolder
from app.agents.hooks import CHAT_SUBMIT, CheckerHook, TraceHook
from app.agents.persona_hooks import style_hooks
from app.agents.persona_run import PersonaRun, tag_agent
from app.agents.prompts import INSTRUCTOR_PROMPT, with_persona
from app.agents.tools import fit_json
from app.agents.trace import Trace
from app.practice.progress import read_progress
from app.practice.progress_view import _exercise_summary
from app.score.api import get_score
from app.score.exceptions import NotConfirmed

log = logging.getLogger(__name__)

RECENT_REPS = 5
INSTRUMENT = "trumpet"  # the app is trumpet only, so the Instructor never hears of another instrument, whatever the session says
REP_RESULT_FIELDS = ("take_id", "tempo_bpm", "status", "passed", "errors", "reasons")


@tool(name=CHAT_SUBMIT.tool_name)
def submit_reply(sentences: list[CoachSentence]) -> dict:
    """Submit your finished reply. Every claim needs its type, id and value; a count claim cites a bar or problem id (b:... or p:...), never a note or extra id. The result says accepted, or lists the sentences to fix before you submit again."""
    return {"accepted": True}  # the CheckerHook replaces this with the Checker's verdict


def _latest_plan(session: Any, take_id: str) -> dict | None:
    plans = [p for p in session.plans.values() if p["take_id"] == take_id]
    return max(plans, key=lambda p: int(p["id"][2:]), default=None)


def plan_progress(session: Any, plan: dict) -> dict:
    """The learner's practice state on the plan's exercises (those in the plan and those practice added for it), by exercise id.

    Each entry is the progress view's exercise summary plus the ladder (current_bpm, streak, fails_in_row) and the
    last few rep results. {} when the plan has no practice state.
    """
    progress = read_progress(session.session_id)
    definitions = {**progress["added_exercises"], **{ex["id"]: ex for ex in plan["exercises"]}}
    summaries = {}
    for exercise_id, state in progress["exercises"].items():
        if state["plan_id"] != plan["id"]:
            continue
        if exercise_id not in definitions:
            log.warning("Exercise %s of session %s has practice state but no definition; left out of the plan progress",
                        exercise_id, session.session_id)
            continue
        reps = [progress["reps"][rep_id] for rep_id in state["rep_ids"] if rep_id in progress["reps"]]
        summaries[exercise_id] = {
            **_exercise_summary(definitions[exercise_id], state, progress["reps"]),
            "current_bpm": state["current_bpm"], "streak": state["streak"], "fails_in_row": state["fails_in_row"],
            "rep_results": [{k: rep.get(k) for k in REP_RESULT_FIELDS} for rep in reps[-RECENT_REPS:]],
        }
    return {"exercises": summaries} if summaries else {}


def make_chat_tools(session_id: str, take: dict) -> dict[str, Callable[..., str]]:
    """The tools only the Instructor has: the score's summary and the take's practice plan."""

    def get_score_summary() -> str:
        """The piece's title, the instrument, how many bars it has, the bars of this take and the target tempo."""
        title = bars = None
        try:
            score = get_score(session_id)
            title, bars = score.title, len(score.bars)
        except (NotConfirmed, OSError, ValueError):
            log.exception("No confirmed score to summarise for session %s", session_id)
        diagnosis = take.get("diagnosis") or {}
        return fit_json({"title": title, "instrument": INSTRUMENT, "bars": bars,
                         "bar_from": take["bar_from"], "bar_to": take["bar_to"],
                         "target_bpm": diagnosis.get("target_bpm", take.get("tempo_bpm"))})

    def get_plan() -> str:
        """The take's practice plan with the learner's progress on it, or null when the take has no plan."""
        session = store.get(session_id)
        plan = _latest_plan(session, take["take_id"])
        if plan is None:
            return json.dumps(None)
        progress = plan_progress(session, plan)
        return fit_json({**plan, **({"progress": progress} if progress else {})})

    return {fn.__name__: fn for fn in (get_score_summary, get_plan)}


def build_instructor_agent(model: Any, tools: dict[str, Callable[..., str]], ctx: CheckContext, holder: ReplyHolder,
                           trace: Trace, history: list[dict], style: PersonaRun = PersonaRun()) -> Agent:
    """`history` is the messages this coach style wrote or heard."""
    persona = style.persona
    agent = Agent(
        model=model,
        tools=[*[tool(fn) for fn in tools.values()], submit_reply],
        system_prompt=with_persona(INSTRUCTOR_PROMPT, persona, "instructor"),
        messages=history,
        hooks=[TraceHook(trace, "instructor"), *style_hooks(style.persona, CHAT_SUBMIT, trace, "instructor"),
               CheckerHook(CHAT_SUBMIT, ctx, holder, trace)],
        callback_handler=None,
    )
    return tag_agent(agent, style)
