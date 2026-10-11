"""Read-only measurement tools for the Coach and Planner agents.

make_tools() returns plain functions with type hints and docstrings, so a later task can
wrap each one with Strands @tool. Each returns JSON of at most MAX_JSON_CHARS characters
and never raises: bad input or missing data comes back as {"error": ...}.
"""
import json
import logging
from typing import Any, Callable, Optional

from app.agents.context import CheckContext, ContextError, build_context, item_kind, no_form, no_history
from app.diagnosis.priority import priority_key

log = logging.getLogger(__name__)

MAX_JSON_CHARS = 8000
MAX_TIER = 3
STATUSES = ("ok", "wrong", "missed", "uncertain")


class ToolInputError(Exception):
    """The caller passed something the tool cannot use; the message says what to fix."""


def fit_json(payload: dict, max_chars: int = MAX_JSON_CHARS) -> str:
    """JSON of the payload, cutting list items from the end until it fits.

    Lists arrive sorted by importance (problems: notes, then rushing / dragging, then slips), so what is cut is the least important. The cut is
    recorded under 'truncated' as the number of items dropped per list.
    """
    dropped: dict[str, int] = {}
    while True:
        body = {**payload, "truncated": dict(dropped)} if dropped else payload
        text = json.dumps(body, separators=(",", ":"))
        if len(text) <= max_chars:
            return text
        lists = [k for k, v in payload.items() if isinstance(v, list) and v]
        if not lists:
            log.error("tool result of %d chars has nothing left to cut", len(text))
            return json.dumps({"error": f"result too large ({len(text)} chars) and cannot be cut"})
        longest = max(lists, key=lambda k: len(json.dumps(payload[k])))
        payload = {**payload, longest: payload[longest][:-1]}
        dropped[longest] = dropped.get(longest, 0) + 1


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ToolInputError(f"{name} must be a whole number")
    try:
        number = float(value)
    except ValueError:
        raise ToolInputError(f"{name} must be a whole number") from None
    if number != int(number):
        raise ToolInputError(f"{name} must be a whole number")
    return int(number)


def _by_score(items: list[dict], key: str = "score") -> list[dict]:
    return sorted(items, key=lambda i: i.get(key, 0), reverse=True)


def _overview(ctx: CheckContext) -> dict:
    d = ctx.diagnosis
    bounds = ctx.bar_range
    counts = {s: sum(1 for n in d.get("notes") or [] if n.get("status") == s) for s in STATUSES}
    counts["extra"] = len(d.get("extras") or [])
    return {
        "cant_tell": d.get("cant_tell"),
        "cant_tell_reason": d.get("cant_tell_reason"),
        "alignment_quality": d.get("alignment_quality"),
        "played_bpm": d.get("played_bpm"),
        "target_bpm": d.get("target_bpm"),
        "clean_bpm": ctx.clean_bpm,
        "counts": counts,
        "tier1": d.get("tier1") or [],
        "form_status": ctx.form.get("status"),
        "tracking_quality": ctx.form.get("tracking_quality"),
        "instrument": ctx.form.get("instrument", d.get("instrument")),
        "bar_from": bounds[0] if bounds else None,
        "bar_to": bounds[1] if bounds else None,
    }


def _problems(ctx: CheckContext, max_tier: Any) -> dict:
    tier = _as_int(max_tier, "max_tier")
    if not 1 <= tier <= MAX_TIER:
        raise ToolInputError(f"max_tier must be 1 to {MAX_TIER}")
    shown = [p for p in ctx.diagnosis.get("problems") or [] if p.get("tier", MAX_TIER) <= tier]
    return {"problems": sorted(shown, key=priority_key)}


def _bar(ctx: CheckContext, bar: Any) -> dict:
    number = _as_int(bar, "bar")
    bounds = ctx.bar_range
    result = next((b for b in ctx.diagnosis.get("bars") or [] if b["bar"] == number), None)
    if bounds is None or result is None:
        span = f"{bounds[0]}-{bounds[1]}" if bounds else "none"
        raise ToolInputError(f"bar out of range {span}")
    notes = [n for n in ctx.diagnosis.get("notes") or [] if n.get("bar") == number]
    flags = [f for f in ctx.form_flags if number in (f.get("bars") or [])]
    return {
        "bar": result,
        "notes": sorted(notes, key=lambda n: n.get("idx", 0)),
        "form_flags": _by_score(flags, "severity"),
    }


def _measurement(ctx: CheckContext, item_id: Any) -> dict:
    item = ctx.find(item_id) if item_kind(item_id) else None
    if item is None:
        raise ToolInputError("unknown id")
    return {"item": item}


def _form_flags(ctx: CheckContext) -> dict:
    return {"flags": _by_score(ctx.form_flags, "severity"), "rules_skipped": ctx.form.get("rules_skipped") or []}


def _history(ctx: CheckContext) -> dict:
    takes = [
        {"take_id": t.get("take_id"), "error_rate": t.get("error_rate"), "played_bpm": t.get("played_bpm")}
        for t in ctx.history
    ]
    return {"takes": takes, "clean_bpm": ctx.clean_bpm}


def make_tools(
    session_id: str,
    take_id: str,
    *,
    get_diagnosis: Callable[[str, str], Optional[dict]],
    lookup: Optional[Callable[[str, str, str], Optional[dict]]] = None,
    get_form: Callable[[str, str], Optional[dict]] = no_form,
    get_earlier_takes: Callable[[str, str], Optional[list]] = no_history,
) -> dict[str, Callable[..., str]]:
    """The six measurement tools for one take, by name.

    All data comes through the injected callables, each called with (session_id, take_id):
      get_diagnosis -> the take's diagnosis dict, or None
      lookup(session_id, take_id, item_id) -> a stored measurement, or None
        (without it, ids are resolved from the diagnosis and form flags)
      get_form -> { status, tracking_quality, instrument, flags, rules_skipped }
      get_earlier_takes -> earlier takes on the same bars [{ take_id, error_rate, played_bpm }]
    """

    def run(body: Callable[..., dict], *args: Any) -> str:
        try:
            ctx = build_context(session_id, take_id, get_diagnosis, lookup, get_form, get_earlier_takes)
            return fit_json(body(ctx, *args))
        except (ToolInputError, ContextError) as exc:
            return json.dumps({"error": str(exc)})
        except Exception as exc:
            log.exception("tool %s failed for take %s", body.__name__, take_id)
            return json.dumps({"error": f"{body.__name__} failed ({type(exc).__name__})"})

    def get_take_overview() -> str:
        """Summary of the take: whether it can be judged, tempos, note counts by status, headline sentences and form status."""
        return run(_overview)

    def list_problems(max_tier: int = 2) -> str:
        """The take's problems up to the given tier (1 to 3), most important first: wrong or missed notes, then rushing or dragging, then small timing slips."""
        return run(_problems, max_tier)

    def get_bar(bar: int) -> str:
        """One bar's result, its notes and the form flags that touch it."""
        return run(_bar, bar)

    def get_measurement(id: str) -> str:
        """Any stored measurement (note, extra, bar, problem or form flag) by its id."""
        return run(_measurement, id)

    def list_form_flags() -> str:
        """The take's form flags, worst first, and the form rules that were skipped."""
        return run(_form_flags)

    def get_history() -> str:
        """Earlier takes on the same bars (error rate and tempo) and the clean tempo."""
        return run(_history)

    tools = (get_take_overview, list_problems, get_bar, get_measurement, list_form_flags, get_history)
    return {tool.__name__: tool for tool in tools}
