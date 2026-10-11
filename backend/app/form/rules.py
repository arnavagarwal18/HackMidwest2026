"""Steps 3 to 6 of the form analysis, as pure functions over per-frame landmarks: measures, baseline, rules, episodes."""
import logging
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean

from . import config
from .bell_measures import BELL_ANGLE, BELL_HEIGHT, FRONT_BELL_SPECS, side_bell_specs
from .episodes import Sample, find_episodes
from .face import FaceResult
from .face_rules import CHEEK_PUFF, FACE_UNAVAILABLE, SMILE, face_samples
from .measures import (ELBOW_ANGLE, ELBOW_GAP_LEFT, ELBOW_GAP_RIGHT, HEAD_DROP, MEASURE_SPECS, NECK_RATIO, TORSO_LEAN,
                       WRIST_BEND, Baseline, Reading, aspect_ratio, compute_baseline, frame_measures)
from .side_measures import HEAD_PITCH, NECK_SIDE, SIDE_TORSO_LEAN, side_specs, with_side_baseline
from .view import FRONT, SIDE, detect_view, near_side

logger = logging.getLogger("app.form")

VIOLIN, TRUMPET = "violin", "trumpet"
BOTH_INSTRUMENTS = (VIOLIN, TRUMPET)
LOW, HIGH = "low", "high"
DEG, RATIO, SCORE = "deg", "ratio", "score"
NOT_VISIBLE = "not_visible"
NOT_FOR_VIEW = "not_for_view"

Readings = dict[str, Reading]


@dataclass(frozen=True)
class Rule:
    """One posture rule. A frame breaks it when `measure` is past `threshold(baseline)` in `direction` (and `also` agrees)."""

    name: str
    instruments: tuple[str, ...]
    measure: str
    direction: str
    unit: str
    threshold: Callable[[Baseline], float | None]  # None when the baseline it needs is missing: the rule is then skipped
    label: str
    side: str | None = None
    fallback_for: str | None = None  # runs only when the named rule is skipped
    # extra condition on the same frame: returns None when its measure is missing, else the extra Reading to require
    also: Callable[[Readings, Baseline], bool | None] | None = None
    views: tuple[str, ...] = (FRONT,)  # camera views the rule runs in
    span_of: Callable[[Baseline], float] | None = None  # severity span when it isn't the fixed one in config

    def span(self, baseline: Baseline) -> float:
        if self.span_of is not None:
            return self.span_of(baseline)
        return config.SEVERITY_SPANS[self.name] if self.fallback_for is None else config.SLOUCHING_FALLBACK_SPAN


def _head_drop_past_fallback(readings: Readings, baseline: Baseline) -> bool | None:
    drop = readings[HEAD_DROP].value
    return None if drop is None else drop > baseline.head_drop + config.SLOUCHING_FALLBACK_HEAD_DROP


def _upper_limit(baseline: Baseline, from_baseline: float, fixed: float) -> float:
    """Threshold for a measure that breaks a rule when it goes above: the stricter of its baseline threshold and the fixed limit.

    A defaulted baseline is a guess (no one was tracked in the first seconds), so only the fixed limit is used then.
    """
    return fixed if baseline.defaulted else min(from_baseline, fixed)


def _lower_limit(baseline: Baseline, from_baseline: float, fixed: float) -> float:
    """Like _upper_limit, for a measure that breaks a rule when it goes below."""
    return fixed if baseline.defaulted else max(from_baseline, fixed)


RULES = [
    Rule("violin_elbow_low", (VIOLIN,), ELBOW_ANGLE, LOW, DEG, lambda b: config.VIOLIN_ELBOW_LOW_DEG,
         "bow elbow too low", side="right"),
    Rule("violin_elbow_high", (VIOLIN,), ELBOW_ANGLE, HIGH, DEG, lambda b: config.VIOLIN_ELBOW_HIGH_DEG,
         "bow elbow too high", side="right"),
    Rule("violin_wrist_collapsed", (VIOLIN,), WRIST_BEND, HIGH, DEG, lambda b: config.VIOLIN_WRIST_COLLAPSED_DEG,
         "left wrist collapsed", side="left"),
    Rule("shoulders_raised", (VIOLIN,), NECK_RATIO, LOW, RATIO,
         lambda b: config.SHOULDERS_RAISED_RATIO * b.neck_ratio, "shoulders raised", side="both"),
    Rule("shoulders_raised", (TRUMPET,), NECK_RATIO, LOW, RATIO,
         lambda b: _lower_limit(b, config.SHOULDERS_RAISED_RATIO * b.neck_ratio, config.TRUMPET_NECK_RATIO_MIN),
         "shoulders raised", side="both"),
    Rule("slouching", BOTH_INSTRUMENTS, TORSO_LEAN, HIGH, DEG, lambda b: config.SLOUCHING_TORSO_LEAN_DEG,
         "slouching"),
    Rule("slouching", BOTH_INSTRUMENTS, NECK_RATIO, LOW, RATIO,
         lambda b: config.SLOUCHING_FALLBACK_NECK_RATIO * b.neck_ratio, "slouching",
         fallback_for="slouching", also=_head_drop_past_fallback),
    Rule("trumpet_head_down", (TRUMPET,), HEAD_DROP, HIGH, RATIO,
         lambda b: _upper_limit(b, b.head_drop + config.TRUMPET_HEAD_DOWN_DROP, config.TRUMPET_HEAD_DROP_MAX), "head dropped"),
    Rule("trumpet_elbows_pinned", (TRUMPET,), ELBOW_GAP_LEFT, LOW, RATIO,
         lambda b: config.TRUMPET_ELBOWS_PINNED_GAP, "left elbow pinned to the body", side="left"),
    Rule("trumpet_elbows_pinned", (TRUMPET,), ELBOW_GAP_RIGHT, LOW, RATIO,
         lambda b: config.TRUMPET_ELBOWS_PINNED_GAP, "right elbow pinned to the body", side="right"),
    Rule("trumpet_elbows_wide", (TRUMPET,), ELBOW_GAP_LEFT, HIGH, RATIO,
         lambda b: config.TRUMPET_ELBOWS_WIDE_GAP, "left elbow held wide of the body", side="left"),
    Rule("trumpet_elbows_wide", (TRUMPET,), ELBOW_GAP_RIGHT, HIGH, RATIO,
         lambda b: config.TRUMPET_ELBOWS_WIDE_GAP, "right elbow held wide of the body", side="right"),
    Rule("trumpet_bell_angle", (TRUMPET,), BELL_HEIGHT, LOW, RATIO,
         lambda b: config.TRUMPET_BELL_HEIGHT_MIN, "bell too high"),
    Rule("trumpet_bell_angle", (TRUMPET,), BELL_HEIGHT, HIGH, RATIO,
         lambda b: config.TRUMPET_BELL_HEIGHT_MAX, "bell too low"),
    # Side view (LLD-4 change 7): the near-side measures; elbows pinned has no side rule
    Rule("shoulders_raised", (VIOLIN,), NECK_SIDE, LOW, RATIO,
         lambda b: None if b.neck_side is None else config.SIDE_NECK_RATIO * b.neck_side, "shoulders raised",
         side="both", views=(SIDE,), span_of=lambda b: config.SIDE_NECK_SPAN_FRACTION * b.neck_side),
    Rule("shoulders_raised", (TRUMPET,), NECK_SIDE, LOW, RATIO,
         lambda b: None if b.neck_side is None else _lower_limit(b, config.SIDE_NECK_RATIO * b.neck_side, config.TRUMPET_NECK_SIDE_MIN),
         "shoulders raised", side="both", views=(SIDE,), span_of=lambda b: config.SIDE_NECK_SPAN_FRACTION * b.neck_side),
    Rule("slouching", BOTH_INSTRUMENTS, SIDE_TORSO_LEAN, HIGH, DEG, lambda b: config.SLOUCHING_TORSO_LEAN_DEG,
         "slouching", views=(SIDE,), span_of=lambda b: config.SEVERITY_SPANS["slouching"]),
    Rule("trumpet_head_down", (TRUMPET,), HEAD_PITCH, HIGH, DEG,
         lambda b: _upper_limit(b, b.head_pitch + config.SIDE_HEAD_PITCH_DELTA, config.TRUMPET_HEAD_PITCH_MAX),
         "head dropped", views=(SIDE,), span_of=lambda b: config.SIDE_HEAD_PITCH_SPAN_DEG),
    Rule("trumpet_bell_angle", (TRUMPET,), BELL_ANGLE, HIGH, DEG, lambda b: config.TRUMPET_BELL_ANGLE_MAX, "bell too high",
         views=(SIDE,), span_of=lambda b: config.SIDE_BELL_ANGLE_SPAN_DEG),
    Rule("trumpet_bell_angle", (TRUMPET,), BELL_ANGLE, LOW, DEG, lambda b: config.TRUMPET_BELL_ANGLE_MIN, "bell too low",
         views=(SIDE,), span_of=lambda b: config.SIDE_BELL_ANGLE_SPAN_DEG),
]

FACE_RULES = [  # judged on the Face Landmarker's readings (measure names a FaceReading field), not on the pose
    Rule("trumpet_cheeks_puffed", (TRUMPET,), CHEEK_PUFF, HIGH, SCORE, lambda b: config.CHEEK_PUFF_MAX, "cheeks puffing out"),
    Rule("trumpet_smile_embouchure", (TRUMPET,), SMILE, HIGH, SCORE, lambda b: config.SMILE_MAX,
         "mouth corners pulled back (smile embouchure)"),
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
    if threshold is None:
        return Sample(None, None, visibility)
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
        "severity": min(1.0, abs(episode.value - threshold) / rule.span(baseline)),
        "confidence": episode.confidence,
        "side": rule.side,
        "bars": [],
        "linked": [],
    }


def _check_instrument(instrument: str) -> None:
    if instrument not in BOTH_INSTRUMENTS:
        raise ValueError(f"unknown instrument {instrument!r}; form rules exist for {', '.join(BOTH_INSTRUMENTS)}")


def _not_for_view(instrument: str, view: str) -> list[str]:
    """Names of the instrument's rules that have no version for this camera view."""
    names = {rule.name for rule in RULES if instrument in rule.instruments and rule.fallback_for is None}
    in_view = {rule.name for rule in RULES if instrument in rule.instruments and view in rule.views}
    return sorted(names - in_view)


def _active_rules(instrument: str, view: str, readings: list[Readings], baseline: Baseline) -> tuple[list[tuple[Rule, list[Sample]]], list[str]]:
    """The rules to flag with, each with its per-frame samples, and the names of rules skipped for missing landmarks."""
    judged = [(rule, [_sample(rule, r, baseline) for r in readings])
              for rule in RULES if instrument in rule.instruments and view in rule.views]
    usable = [(rule, samples) for rule, samples in judged if _missing_fraction(samples) <= config.MISSING_MAX_FRACTION]
    primary_names = {rule.name for rule, _ in judged if rule.fallback_for is None}
    usable_primary_names = {rule.name for rule, _ in usable if rule.fallback_for is None}
    skipped = sorted(primary_names - usable_primary_names)
    active = [(rule, samples) for rule, samples in usable if rule.fallback_for is None or rule.fallback_for in skipped]
    return active, skipped


def _active_face_rules(face: FaceResult, times: list[float], baseline: Baseline,
                       take_id: str) -> tuple[list[tuple[Rule, list[Sample]]], list[dict]]:
    """The face rules to flag with, each with its per-frame samples, and every one skipped with its reason."""
    if face.unavailable:
        reason = FACE_UNAVAILABLE
    elif face.face_quality is None or face.face_quality < config.FACE_MIN_QUALITY:
        reason = NOT_VISIBLE
    else:
        return [(rule, face_samples(rule.measure, rule.threshold(baseline), times, face)) for rule in FACE_RULES], []
    logger.warning("take %s: face rules skipped (%s), face_quality %s", take_id, reason, face.face_quality)
    return [], [{"rule": rule.name, "reason": reason} for rule in FACE_RULES]


def _view_specs(view: str, frames: list[dict]) -> dict:
    """The measures to take in `view`: the front ones, plus the side ones (for the near body side) in a side view."""
    if view == FRONT:
        return {**MEASURE_SPECS, **FRONT_BELL_SPECS}
    near = near_side(frames)
    return {**MEASURE_SPECS, **side_specs(near), **side_bell_specs(near)}


def analyse(frames: list[dict], instrument: str, take_id: str, width: int | None = None,
            height: int | None = None, face: FaceResult | None = None) -> dict:
    """Judge a take's frames against the posture rules: { view, view_ratio, baseline, rules_skipped, flags }.

    Each frame is { t, pose, left_hand, right_hand }. A rule whose measure is missing in too many frames is listed in
    rules_skipped and never flagged; the slouching torso rule then falls back to the neck and head measures.
    `width` and `height` are the video's pixel size, used so normalised x and y share one scale; None means square.
    A side view (see view.detect_view) is judged with the side measures and rules; the front rules with no side version
    are listed in rules_skipped with reason 'not_for_view'.
    `face` holds the Face Landmarker's readings of a trumpet take (None: not checked); it adds the embouchure rules.
    """
    _check_instrument(instrument)
    aspect = aspect_ratio(width, height)
    frames = sorted(frames, key=lambda f: f["t"])
    times = [f["t"] for f in frames]
    view, view_ratio = detect_view(frames, aspect)
    specs = _view_specs(view, frames)
    readings = [frame_measures(f, aspect, specs) for f in frames]
    baseline = compute_baseline(frames, readings)
    if view == SIDE:
        baseline = with_side_baseline(baseline, frames, readings)
    active, skipped = _active_rules(instrument, view, readings, baseline)
    for name in skipped:
        logger.warning("take %s: rule %s skipped, its measure is missing in over %d%% of frames",
                       take_id, name, round(config.MISSING_MAX_FRACTION * 100))

    face_active, face_skipped = _active_face_rules(face, times, baseline, take_id) if face is not None else ([], [])
    active = active + face_active
    flags = [_flag_fields(rule, baseline, episode) for rule, samples in active for episode in find_episodes(times, samples)]
    flags.sort(key=lambda flag: flag["start_s"])
    flags = [{"id": f"f:{take_id}:{k}", **flag} for k, flag in enumerate(flags, start=1)]
    rules_skipped = ([{"rule": n, "reason": NOT_VISIBLE} for n in skipped]
                     + [{"rule": n, "reason": NOT_FOR_VIEW} for n in _not_for_view(instrument, view)] + face_skipped)
    return {"view": view, "view_ratio": view_ratio, "baseline": baseline.to_dict(), "rules_skipped": rules_skipped,
            "flags": flags}
