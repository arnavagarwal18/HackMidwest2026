"""Step 8: one template sentence per tier-1 problem, built only from the problem's numbers."""
from . import config

LINK_PHRASE = ", at the same time as {kind} in bar {bar}"
DRIFT_DIRECTION = {config.DRIFT_RUSHING: "faster", config.DRIFT_DRAGGING: "slower"}
SECONDS_PER_MINUTE = 60


def bars_label(bars: list[int]) -> str:
    first, last = min(bars), max(bars)
    return f"Bar {first}" if first == last else f"Bars {first}-{last}"


def clock(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), SECONDS_PER_MINUTE)
    return f"{minutes}:{rest:02d}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def _notes_text(numbers: dict) -> str:
    parts = []
    if numbers["wrong"]:
        plural = "" if numbers["wrong"] == 1 else "s"
        played = numbers.get("first_wrong")
        detail = f" (played {played['played']} for {played['expected']})" if played else ""
        parts.append(f"{numbers['wrong']} wrong note{plural}{detail}")
    if numbers["missed"]:
        parts.append(f"{numbers['missed']} missed")
    if numbers["extra"]:
        parts.append(f"{numbers['extra']} extra")
    return _join(parts)


def _form_text(problem: dict) -> str:
    numbers = problem["numbers"]
    link = ""
    if "link_kind" in numbers:
        link = LINK_PHRASE.format(kind=numbers["link_kind"], bar=numbers["link_bar"])
    return f"{clock(problem['first_time_s'])}: {numbers['label'].rstrip('.')}{link}"


def _body(problem: dict) -> str:
    kind, numbers = problem["kind"], problem["numbers"]
    if kind == config.PROBLEM_NOTES:
        return _notes_text(numbers)
    if kind in (config.TIMING_LATE, config.TIMING_EARLY):
        return f"{numbers['count']} notes {kind}, {round(numbers['mean_ms'])} ms on average"
    return f"{kind}, about {round(numbers['drift_pct'])}% {DRIFT_DIRECTION[kind]} than {numbers['target_bpm']:g} BPM"


def sentence_text(problem: dict) -> str:
    """'Bar 12: 2 wrong notes (played F#4 for F4) and 1 missed.' and its siblings."""
    label = bars_label(problem["bars"])
    if problem["kind"] == config.PROBLEM_FORM:
        return f"{label}, {_form_text(problem)}."
    return f"{label}: {_body(problem)}."


def build_sentence(problem: dict) -> dict:
    return {
        "problem_id": problem["id"],
        "text": sentence_text(problem),
        "measurement_ids": problem["measurement_ids"],
        "jump": {"bar": min(problem["bars"]), "time_s": problem["first_time_s"]},
    }
