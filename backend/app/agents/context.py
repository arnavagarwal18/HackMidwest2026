"""Take data shared by the Checker and the measurement tools.

Everything is read through injected callables, so this module needs neither the
diagnosis module nor a model.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

CLEAN_ERROR_RATE = 0.05  # a take at or under this error rate counts as clean
_KIND_BY_PREFIX = {"n": "note", "x": "extra", "b": "bar", "p": "problem", "f": "flag"}


class ContextError(Exception):
    """The take data needed to answer is not available."""


def item_kind(item_id: Any) -> Optional[str]:
    """'note', 'extra', 'bar', 'problem' or 'flag' from an id like 'n:t1:2:0'."""
    if not isinstance(item_id, str) or ":" not in item_id:
        return None
    return _KIND_BY_PREFIX.get(item_id.split(":", 1)[0])


def item_bars(item: dict) -> list[int]:
    """The bar numbers an item lies in."""
    if isinstance(item.get("bars"), list):
        return [b for b in item["bars"] if isinstance(b, int)]
    if isinstance(item.get("bar"), int):
        return [item["bar"]]
    return []


def index_items(diagnosis: dict, form_flags: list[dict]) -> dict[str, dict]:
    """Every measurement of a take by id: notes, extras, bars, problems, form flags."""
    items = {}
    for key in ("notes", "extras", "bars", "problems"):
        for item in diagnosis.get(key) or []:
            items[item["id"]] = item
    for flag in form_flags:
        items[flag["id"]] = flag
    return items


def clean_tempo(history: list[dict], own: dict) -> Optional[float]:
    """Fastest tempo at which this take or an earlier one on the same bars was clean."""
    tempos = [
        t["played_bpm"]
        for t in [*history, own]
        if isinstance(t.get("error_rate"), (int, float))
        and t["error_rate"] <= CLEAN_ERROR_RATE
        and isinstance(t.get("played_bpm"), (int, float))
    ]
    return max(tempos) if tempos else None


@dataclass
class CheckContext:
    """One take's data as the Checker and the tools see it."""

    lookup: Callable[[str], Optional[dict]]
    diagnosis: dict
    form: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)

    def find(self, item_id: Any) -> Optional[dict]:
        """The stored item for an id, or None when unknown (or the lookup failed)."""
        if not isinstance(item_id, str):
            return None
        try:
            return self.lookup(item_id)
        except Exception:
            log.exception("lookup failed for id %s", item_id)
            return None

    @property
    def form_flags(self) -> list[dict]:
        return self.form.get("flags") or []

    @property
    def flag_rules(self) -> set[str]:
        return {f.get("rule") for f in self.form_flags}

    @property
    def bar_range(self) -> Optional[tuple[int, int]]:
        bars = [b["bar"] for b in self.diagnosis.get("bars") or []]
        return (min(bars), max(bars)) if bars else None

    @property
    def target_bpm(self) -> Optional[float]:
        return self.diagnosis.get("target_bpm")

    @property
    def clean_bpm(self) -> Optional[float]:
        own = {"error_rate": self.diagnosis.get("error_rate"), "played_bpm": self.diagnosis.get("played_bpm")}
        return clean_tempo(self.history, own)


def no_form(session_id: str, take_id: str) -> dict:
    return {}


def no_history(session_id: str, take_id: str) -> list:
    return []


def build_context(
    session_id: str,
    take_id: str,
    get_diagnosis: Callable[[str, str], Optional[dict]],
    lookup: Optional[Callable[[str, str, str], Optional[dict]]] = None,
    get_form: Callable[[str, str], Optional[dict]] = no_form,
    get_earlier_takes: Callable[[str, str], Optional[list]] = no_history,
) -> CheckContext:
    """Load a take's data through the injected callables.

    Raises ContextError with a message the caller can act on when the take has no diagnosis.
    Without a `lookup`, ids are resolved from the diagnosis and form flags themselves.
    """
    diagnosis = get_diagnosis(session_id, take_id)
    if not isinstance(diagnosis, dict):
        raise ContextError(f"no diagnosis for take {take_id}")
    form = get_form(session_id, take_id) or {}
    history = get_earlier_takes(session_id, take_id) or []
    if lookup is None:
        index = index_items(diagnosis, form.get("flags") or [])
        bound = index.get
    else:
        def bound(item_id: str) -> Optional[dict]:
            return lookup(session_id, take_id, item_id)
    return CheckContext(lookup=bound, diagnosis=diagnosis, form=form, history=history)
