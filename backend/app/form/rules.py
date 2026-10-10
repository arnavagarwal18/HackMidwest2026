"""Steps 3 to 6 of the form analysis, as pure functions over per-frame landmarks: measures, baseline, rules, episodes."""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean

from . import config
from .episodes import Sample, find_episodes
from .measures import (ELBOW_ANGLE, ELBOW_GAP_LEFT, ELBOW_GAP_RIGHT, HEAD_DROP, NECK_RATIO, TORSO_LEAN, WRIST_BEND,
                       Baseline, Reading, aspect_ratio, compute_baseline, frame_measures)

logger = logging.getLogger("app.form")

VIOLIN, TRUMPET = "violin", "trumpet"
BOTH_INSTRUMENTS = (VIOLIN, TRUMPET)
LOW, HIGH = "low", "high"
DEG, RATIO = "deg", "ratio"
NOT_VISIBLE = "not_visible"

Readings = dict[str, Reading]


@dataclass(frozen=True)
class Rule:
    """One posture rule. A frame breaks it when `measure` is past `threshold(baseline)` in `direction` (and `also` agrees)."""

    name: str
    instruments: tuple[str, ...]
    measure: str
    direction: str
    unit: str
    threshold: Callable[[Baseline], float]
    label: str
    side: str | None = None
    fallback_for: str | None = None  # runs only when the named rule is skipped
    # extra condition on the same frame: returns None when its measure is missing, else the extra Reading to require
    also: Callable[[Readings, Baseline], bool | None] | None = None

    @property
    def span(self) -> float:
        return config.SEVERITY_SPANS[self.name] if self.fallback_for is None else config.SLOUCHING_FALLBACK_SPAN


def _head_drop_past_fallback(readings: Readings, baseline: Baseline) -> bool | None:
    drop = readings[HEAD_DROP].value
    return None if drop is None else drop > baseline.head_drop + config.SLOUCHING_FALLBACK_HEAD_DROP


RULES = [
    Rule("violin_elbow_low", (VIOLIN,), ELBOW_ANGLE, LOW, DEG, lambda b: config.VIOLIN_ELBOW_LOW_DEG,
         "bow elbow too low", side="right"),
    Rule("violin_elbow_high", (VIOLIN,), ELBOW_ANGLE, HIGH, DEG, lambda b: config.VIOLIN_ELBOW_HIGH_DEG,
         "bow elbow too high", side="right"),
    Rule("violin_wrist_collapsed", (VIOLIN,), WRIST_BEND, HIGH, DEG, lambda b: config.VIOLIN_WRIST_COLLAPSED_DEG,
         "left wrist collapsed", side="left"),
    Rule("shoulders_raised", BOTH_INSTRUMENTS, NECK_RATIO, LOW, RATIO,
         lambda b: config.SHOULDERS_RAISED_RATIO * b.neck_ratio, "shoulders raised", side="both"),
    Rule("slouching", BOTH_INSTRUMENTS, TORSO_LEAN, HIGH, DEG, lambda b: config.SLOUCHING_TORSO_LEAN_DEG,
         "slouching"),
    Rule("slouching", BOTH_INSTRUMENTS, NECK_RATIO, LOW, RATIO,
         lambda b: config.SLOUCHING_FALLBACK_NECK_RATIO * b.neck_ratio, "slouching",
         fallback_for="slouching", also=_head_drop_past_fallback),
    Rule("trumpet_head_down", (TRUMPET,), HEAD_DROP, HIGH, RATIO,
         lambda b: b.head_drop + config.TRUMPET_HEAD_DOWN_DROP, "head dropped"),
    Rule("trumpet_elbows_pinned", (TRUMPET,), ELBOW_GAP_LEFT, LOW, RATIO,
         lambda b: config.TRUMPET_ELBOWS_PINNED_GAP, "left elbow pinned to the body", side="left"),
    Rule("trumpet_elbows_pinned", (TRUMPET,), ELBOW_GAP_RIGHT, LOW, RATIO,
         lambda b: config.TRUMPET_ELBOWS_PINNED_GAP, "right elbow pinned to the body", side="right"),
]


def _sample(rule: Rule, readings: Readings, baseline: Baseline) -> Sample:
    reading = readings[rule.measure]
    visibility = reading.visibility
    if rule.also is not None:
        visibility = mean((visibility, readings[HEAD_DROP].visibility))
    extra = rule.also(readings, baseline) if rule.also is not None else True
    if reading.value is None or extra is None:
        return Sample(None, None, visibility)
    threshold = rule.threshold(baseline)
    excess = threshold - reading.value if rule.direction == LOW else reading.value - threshold
    if extra is False:
        excess = min(excess, 0.0)  # present, but the extra condition says the frame is fine
    return Sample(reading.value, excess, visibility)


def _missing_fraction(samples: list[Sample]) -> float:
    if not samples:
        return 1.0
    return sum(s.value is None or s.excess is None for s in samples) / len(samples)


def _flag_fields(rule: Rule, baseline: Baseline, episode) -> dict:
    threshold = rule.threshold(baseline)
    return {
        "rule": rule.name,
        "label": rule.label,
        "start_s": episode.start_s,
        "end_s": episode.end_s,
        "peak_s": episode.peak_s,
        "value": episode.value,
        "threshold": threshold,
        "unit": rule.unit,
        "direction": rule.direction,
        "severity": min(1.0, abs(episode.value - threshold) / rule.span),
        "confidence": episode.confidence,
        "side": rule.side,
        "bars": [],
        "linked": [],
    }


def _check_instrument(instrument: str) -> None:
    if instrument not in BOTH_INSTRUMENTS:
        raise ValueError(f"unknown instrument {instrument!r}; form rules exist for {', '.join(BOTH_INSTRUMENTS)}")


def _active_rules(instrument: str, readings: list[Readings], baseline: Baseline) -> tuple[list[tuple[Rule, list[Sample]]], list[str]]:
    """The rules to flag with, each with its per-frame samples, and the names of rules skipped for missing landmarks."""
    judged = [(rule, [_sample(rule, r, baseline) for r in readings]) for rule in RULES if instrument in rule.instruments]
    usable = [(rule, samples) for rule, samples in judged if _missing_fraction(samples) <= config.MISSING_MAX_FRACTION]
    primary_names = {rule.name for rule, _ in judged if rule.fallback_for is None}
    usable_primary_names = {rule.name for rule, _ in usable if rule.fallback_for is None}
    skipped = sorted(primary_names - usable_primary_names)
    active = [(rule, samples) for rule, samples in usable if rule.fallback_for is None or rule.fallback_for in skipped]
    return active, skipped


def analyse(frames: list[dict], instrument: str, take_id: str, width: int | None = None,
            height: int | None = None) -> dict:
    """Judge a take's frames against the posture rules: { baseline, rules_skipped, flags }.

    Each frame is { t, pose, left_hand, right_hand }. A rule whose measure is missing in too many frames is listed in
    rules_skipped and never flagged; the slouching torso rule then falls back to the neck and head measures.
    `width` and `height` are the video's pixel size, used so normalised x and y share one scale; None means square.
    """
    _check_instrument(instrument)
    aspect = aspect_ratio(width, height)
    frames = sorted(frames, key=lambda f: f["t"])
    times = [f["t"] for f in frames]
    readings = [frame_measures(f, aspect) for f in frames]
    baseline = compute_baseline(frames, readings)
    active, skipped = _active_rules(instrument, readings, baseline)
    for name in skipped:
        logger.warning("take %s: rule %s skipped, its measure is missing in over %d%% of frames",
                       take_id, name, round(config.MISSING_MAX_FRACTION * 100))

    flags = [_flag_fields(rule, baseline, episode) for rule, samples in active for episode in find_episodes(times, samples)]
    flags.sort(key=lambda flag: flag["start_s"])
    flags = [{"id": f"f:{take_id}:{k}", **flag} for k, flag in enumerate(flags, start=1)]
    return {"baseline": baseline.to_dict(), "rules_skipped": [{"rule": n, "reason": NOT_VISIBLE} for n in skipped],
            "flags": flags}
