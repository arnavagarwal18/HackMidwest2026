"""Checker rules for a single claim and for the text that makes it (rules a to c)."""
import math
import re
from typing import Any, Iterable, Optional

from app.agents.context import CheckContext, item_bars, item_kind

COUNT_FIELDS = ("wrong", "missed", "extra", "late", "early")
CLAIM_TYPES = ("count", "timing_ms", "direction", "tempo_pct", "pitch", "form", "bar")
DIRECTION_WORDS = ("late", "early", "sharp", "flat", "rushing", "dragging", "fast", "slow", "high", "low")
_CANONICAL_DIRECTION = {"fast": "rushing", "slow": "dragging"}
TIMING_TOLERANCE_MS = 10
TIMING_TOLERANCE_RATIO = 0.10
TEMPO_TOLERANCE_POINTS = 1.5
FORM_TIME_MARGIN_S = 0.5

_NOTE_NAME = re.compile(r"\b[A-G][#b♯♭]?-?\d\b")
_NUMBER_OR_TIME = re.compile(r"(\d+):(\d{2})|(\d+(?:\.\d+)?)")
_DIRECTION_WORD = re.compile(r"\b(" + "|".join(DIRECTION_WORDS) + r")\b", re.IGNORECASE)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def canonical_direction(word: str) -> str:
    word = word.lower()
    return _CANONICAL_DIRECTION.get(word, word)


def _sign_word(value: Any, positive: str, negative: str) -> set[str]:
    if not is_number(value) or value == 0:
        return set()
    return {positive if value > 0 else negative}


def stored_directions(item: dict) -> set[str]:
    """The direction words the stored item supports, from the sign of its numbers."""
    kind = item_kind(item.get("id"))
    if kind == "flag":
        return {canonical_direction(item["direction"])} if item.get("direction") else set()
    numbers = item.get("numbers") or {}
    words = _sign_word(item.get("timing_ms", item.get("mean_timing_ms")), "late", "early")
    words |= _sign_word(item.get("cents_off"), "sharp", "flat")
    words |= _sign_word(item.get("drift_pct", numbers.get("drift_pct")), "rushing", "dragging")
    if kind == "problem" and item.get("kind") in ("late", "early", "rushing", "dragging"):
        words.add(item["kind"])
    return words


def _stored_count(item: dict, field: str) -> Optional[int]:
    numbers = item.get("numbers") or {}
    kind = item_kind(item.get("id"))
    if kind == "bar" and field in ("wrong", "missed", "extra"):
        return item.get(field)
    if kind == "problem":
        if field in numbers:
            return numbers[field]
        if field == item.get("kind") and field in ("late", "early"):
            return numbers.get("count")
    return None


def _stored_timing(item: dict) -> Optional[float]:
    numbers = item.get("numbers") or {}
    for value in (item.get("timing_ms"), item.get("mean_timing_ms"), numbers.get("mean_ms")):
        if is_number(value):
            return value
    return None


def _stored_drift(item: dict) -> Optional[float]:
    value = item.get("drift_pct", (item.get("numbers") or {}).get("drift_pct"))
    return value if is_number(value) else None


def _check_count(claim: dict, item: dict) -> Optional[str]:
    field = claim.get("field")
    if field not in COUNT_FIELDS:
        return f"bad claim: count field must be one of {', '.join(COUNT_FIELDS)}"
    stored = _stored_count(item, field)
    if stored is None:
        return f"count mismatch: {claim['id']} has no stored {field} count"
    if claim["value"] != stored:
        return f"count mismatch: claimed {claim['value']}, stored {stored}"
    return None


def _check_timing(claim: dict, item: dict) -> Optional[str]:
    stored = _stored_timing(item)
    if stored is None:
        return f"timing mismatch: {claim['id']} has no stored timing"
    gap = abs(claim["value"] - stored)
    if gap > TIMING_TOLERANCE_MS and gap > TIMING_TOLERANCE_RATIO * abs(stored):
        return f"timing mismatch: claimed {claim['value']} ms, stored {stored} ms"
    return None


def _check_direction(claim: dict, item: dict) -> Optional[str]:
    value = claim.get("value")
    if not isinstance(value, str) or value.lower() not in DIRECTION_WORDS:
        return "bad claim: direction value is not a known direction word"
    allowed = stored_directions(item)
    if canonical_direction(value) not in allowed:
        stored = ", ".join(sorted(allowed)) or "none"
        return f"direction mismatch: claimed {value}, stored {stored}"
    return None


def _check_tempo(claim: dict, item: dict) -> Optional[str]:
    stored = _stored_drift(item)
    if stored is None:
        return f"tempo mismatch: {claim['id']} has no stored drift"
    # The sign is carried by the direction claim, so the size may be given without it.
    if min(abs(claim["value"] - stored), abs(abs(claim["value"]) - abs(stored))) > TEMPO_TOLERANCE_POINTS:
        return f"tempo mismatch: claimed {claim['value']}%, stored {stored}%"
    return None


def _check_pitch(claim: dict, item: dict) -> Optional[str]:
    if claim.get("value") != item.get("played_name"):
        return f"pitch mismatch: claimed {claim.get('value')}, stored {item.get('played_name')}"
    return None


def _check_form(claim: dict, item: dict) -> Optional[str]:
    if item_kind(item.get("id")) != "flag":
        return f"form mismatch: {claim['id']} is not a form flag"
    if claim.get("value") != item.get("rule"):
        return f"form mismatch: claimed rule {claim.get('value')}, stored {item.get('rule')}"
    time_s = claim.get("time_s")
    if not is_number(time_s):
        return "bad claim: form claim needs time_s"
    if not item["start_s"] - FORM_TIME_MARGIN_S <= time_s <= item["end_s"] + FORM_TIME_MARGIN_S:
        return f"form mismatch: time {time_s}s outside {item['start_s']}-{item['end_s']}s"
    return None


def _check_bar(claim: dict, item: dict) -> Optional[str]:
    if claim["value"] not in item_bars(item):
        return f"bar mismatch: {claim['id']} lies in bars {item_bars(item)}, not {claim['value']}"
    return None


_CHECKS = {
    "count": _check_count,
    "timing_ms": _check_timing,
    "direction": _check_direction,
    "tempo_pct": _check_tempo,
    "pitch": _check_pitch,
    "form": _check_form,
    "bar": _check_bar,
}
_NUMERIC_TYPES = ("count", "timing_ms", "tempo_pct", "bar")


def check_claim(claim: Any, ctx: CheckContext) -> Optional[str]:
    """None when the claim holds against the stored item, else the reason it fails."""
    if not isinstance(claim, dict) or claim.get("type") not in CLAIM_TYPES:
        return "bad claim: type must be one of " + ", ".join(CLAIM_TYPES)
    item = ctx.find(claim.get("id"))
    if item is None:
        return "unknown id: " + str(claim.get("id"))
    if claim["type"] in _NUMERIC_TYPES and not is_number(claim.get("value")):
        return "bad claim: value must be a number"
    return _CHECKS[claim["type"]](claim, item)


def claim_numbers(claims: Iterable[dict]) -> list[float]:
    """Every number the claims commit to: values and form times (signs dropped)."""
    numbers = []
    for claim in claims:
        for key in ("value", "time_s"):
            if is_number(claim.get(key)):
                numbers.append(abs(claim[key]))
    return numbers


def text_numbers(text: str) -> list[tuple[str, float]]:
    """Every number or m:ss time written in the text, as (as written, value).

    Digits inside a note name such as F#5 are pitch names, not numbers, and are skipped.
    """
    found = []
    for match in _NUMBER_OR_TIME.finditer(_NOTE_NAME.sub(" ", text)):
        value = int(match.group(1)) * 60 + int(match.group(2)) if match.group(1) else float(match.group(3))
        found.append((match.group(0), value))
    return found


def check_text(text: str, claims: list[dict], allowed_numbers: Iterable[float]) -> list[str]:
    """Reasons the text says something no claim or cited bar backs (rule c)."""
    allowed = {round_half_up(n) for n in [*claim_numbers(claims), *allowed_numbers]}
    reasons = [
        f"stray number: {written} in text is not a claim value, cited bar or jump time"
        for written, value in text_numbers(text)
        if round_half_up(value) not in allowed
    ]
    claimed = {
        canonical_direction(c["value"])
        for c in claims
        if c.get("type") == "direction" and isinstance(c.get("value"), str)
    }
    for word in sorted({canonical_direction(w) for w in _DIRECTION_WORD.findall(text)} - claimed):
        reasons.append(f"unclaimed direction: '{word}' in text has no matching direction claim")
    return reasons
