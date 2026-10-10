"""Steps 7 and 8 of the form analysis: put each flag on score bars, then link it to what the note diagnosis found there."""
import json
import logging

from .. import store
from ..diagnosis import config as diagnosis_config
from ..diagnosis.timing import timing_flag
from . import config

logger = logging.getLogger("app.form")

SCORE_FILE = "score.json"
NOTES_LINK = "notes"
WRONG_OR_MISSED = (diagnosis_config.STATUS_WRONG, diagnosis_config.STATUS_MISSED)
DRIFT_KINDS = (diagnosis_config.DRIFT_RUSHING, diagnosis_config.DRIFT_DRAGGING)


def read_bar_spans(session_id: str, bar_from: int, bar_to: int) -> list[dict]:
    """{bar, start_beat, beats} of the take's bars in order, from score.json; [] (logged) when the score can't be read."""
    path = store.session_dir(session_id) / SCORE_FILE
    try:
        bars = json.loads(path.read_text(encoding="utf-8"))["bars"]
    except (OSError, ValueError, KeyError):
        logger.warning("Could not read the score bars from %s; flags of session %s get no bars", path, session_id, exc_info=True)
        return []
    spans = [{key: bar[key] for key in ("bar", "start_beat", "beats")} for bar in bars if bar_from <= bar["bar"] <= bar_to]
    return sorted(spans, key=lambda span: span["start_beat"])


def has_grid(diagnosis: dict | None) -> bool:
    """True when the diagnosis could tell where the beats fall (a can't-tell take has no usable grid)."""
    grid = (diagnosis or {}).get("grid")
    return bool(grid) and not diagnosis.get("cant_tell") and grid.get("offset_s") is not None and bool(grid.get("sec_per_beat"))


def bars_between(start_s: float, end_s: float, grid: dict, spans: list[dict]) -> list[int]:
    """Numbers of the bars from the one holding start_s to the one holding end_s; times outside the take's bars give none.

    Video time t is beat (t - offset_s) / sec_per_beat from the start of the first bar.
    """
    if not spans:
        return []
    first_beat = spans[0]["start_beat"]

    def beat_at(seconds: float) -> float:
        return (seconds - grid["offset_s"]) / grid["sec_per_beat"] + first_beat

    start_beat, end_beat = beat_at(start_s), beat_at(end_s)
    return [span["bar"] for span in spans if span["start_beat"] <= end_beat and start_beat < span["start_beat"] + span["beats"]]


def _link(kind: str, bar_result: dict, notes: list[dict]) -> dict:
    return {"kind": kind, "bar": bar_result["bar"], "ids": [bar_result["id"], *(note["id"] for note in notes)]}


def links_for_bar(bar_result: dict, notes: list[dict], extras: list[dict]) -> list[dict]:
    """Links from one bar's result: notes, late, early, rushing, dragging; `notes` and `extras` are that bar's own."""
    links = []
    wrong_or_missed = [note for note in notes if note["status"] in WRONG_OR_MISSED]
    if wrong_or_missed or extras:
        links.append(_link(NOTES_LINK, bar_result, [*wrong_or_missed, *extras]))
    for kind in (diagnosis_config.TIMING_LATE, diagnosis_config.TIMING_EARLY):
        off_beat = [note for note in notes if timing_flag(note.get("timing_ms")) == kind]
        if len(off_beat) >= config.LINK_MIN_TIMING_NOTES:
            links.append(_link(kind, bar_result, off_beat))
    if bar_result.get("drift") in DRIFT_KINDS:
        links.append(_link(bar_result["drift"], bar_result, []))
    return links


def _in_bar(items: list[dict], bar: int) -> list[dict]:
    return [item for item in items if item["bar"] == bar]


def add_bars_and_links(flags: list[dict], diagnosis: dict | None, spans: list[dict]) -> list[dict]:
    """The flags with `bars` and `linked` filled in; both stay empty without a usable grid from the note diagnosis."""
    if not has_grid(diagnosis):
        return [{**flag, "bars": [], "linked": []} for flag in flags]
    results = {bar["bar"]: bar for bar in diagnosis.get("bars") or []}
    notes, extras = diagnosis.get("notes") or [], diagnosis.get("extras") or []
    placed = []
    for flag in flags:
        bars = bars_between(flag["start_s"], flag["end_s"], diagnosis["grid"], spans)
        linked = [link for bar in bars if bar in results
                  for link in links_for_bar(results[bar], _in_bar(notes, bar), _in_bar(extras, bar))]
        placed.append({**flag, "bars": bars, "linked": linked})
    return placed
