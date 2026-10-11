"""Step 3: line up expected notes with played notes (two Needleman-Wunsch passes) and pick a time grid."""
import logging
from bisect import bisect_right
from dataclasses import dataclass
from statistics import median
from typing import Callable

from . import config
from .expected import ExpectedNote

logger = logging.getLogger("app.diagnosis")

Pair = tuple[int, int]  # (index into expected, index into played), both in time order
# Extra cost of pairing a played note with an expected one; None means the pair is not allowed.
PairPenalty = Callable[[ExpectedNote, dict], float | None]


@dataclass
class Fit:
    offset_s: float
    sec_per_beat: float


@dataclass
class Alignment:
    pairs: list[Pair]
    fit: Fit | None


def _pair_score(expected: ExpectedNote, played: dict) -> float:
    distance = abs(expected.midi - played["midi"])
    if distance == 0:
        return config.SCORE_SAME_MIDI
    if distance <= 1:
        return config.SCORE_WITHIN_SEMITONE
    return config.SCORE_OTHER_SUBSTITUTION


def needleman_wunsch(
    expected: list[ExpectedNote], played: list[dict], pair_penalty: PairPenalty | None = None
) -> list[Pair]:
    """Best global alignment; `pair_penalty` is taken off a pair's score, or forbids it by returning None
    (default: pairs are allowed anywhere, at no extra cost).

    The table scores the notes from each position onward, and the trace-back runs forward preferring
    pairs, so equally good alignments resolve to the earliest matches.
    """
    n, m = len(expected), len(played)
    gap = config.SCORE_GAP
    table = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        table[i][m] = (n - i) * gap
    for j in range(m - 1, -1, -1):
        table[n][j] = (m - j) * gap

    def diagonal(i: int, j: int) -> float | None:
        penalty = 0.0 if pair_penalty is None else pair_penalty(expected[i], played[j])
        if penalty is None:
            return None
        return table[i + 1][j + 1] + _pair_score(expected[i], played[j]) - penalty

    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best = max(table[i + 1][j] + gap, table[i][j + 1] + gap)
            paired = diagonal(i, j)
            table[i][j] = best if paired is None else max(best, paired)

    pairs: list[Pair] = []
    i = j = 0
    while i < n and j < m:
        paired = diagonal(i, j)
        if paired is not None and table[i][j] == paired:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif table[i][j] == table[i + 1][j] + gap:
            i += 1
        else:
            j += 1
    return pairs


def fit_line(points: list[tuple[float, float]], min_points: int = config.MIN_FIT_PAIRS) -> Fit | None:
    """Least squares onset_s = offset_s + beat * sec_per_beat; None if too few or degenerate points."""
    if len(points) < min_points:
        return None
    mean_x = sum(x for x, _ in points) / len(points)
    mean_y = sum(y for _, y in points) / len(points)
    spread = sum((x - mean_x) ** 2 for x, _ in points)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / spread
    if slope <= 0:
        return None
    return Fit(offset_s=mean_y - slope * mean_x, sec_per_beat=slope)


@dataclass
class TimeMap:
    """Expected beat -> played time: straight lines between anchors, the least-squares line beyond them."""

    anchors: list[tuple[float, float]]  # (expected beat, played onset_s), beats and times both rising
    fit: Fit

    def __post_init__(self) -> None:
        self._beats = [beat for beat, _ in self.anchors]

    def time_at(self, beat: float) -> float:
        first, last = self.anchors[0], self.anchors[-1]
        if beat < first[0] or beat > last[0]:
            return self.fit.offset_s + beat * self.fit.sec_per_beat
        upper = min(bisect_right(self._beats, beat), len(self._beats) - 1)
        (beat_a, time_a), (beat_b, time_b) = self.anchors[upper - 1], self.anchors[upper]
        return time_a + (beat - beat_a) / (beat_b - beat_a) * (time_b - time_a)


def _same_midi_anchors(expected: list[ExpectedNote], played: list[dict], pass1: list[Pair]) -> list[tuple[float, float]]:
    """Pass 1's same-midi pairs as (beat, onset_s); one whose onset (or beat) does not move on from the previous
    kept anchor's is dropped."""
    anchors: list[tuple[float, float]] = []
    for e, p in pass1:
        if expected[e].midi != played[p]["midi"]:
            continue
        point = (expected[e].onset_beats, played[p]["onset_s"])
        if not anchors or (point[1] > anchors[-1][1] and point[0] > anchors[-1][0]):
            anchors.append(point)
    return anchors


def _off_line(index: int, anchors: list[tuple[float, float]], sec_per_beat: float) -> bool:
    """True when the anchor's onset is more than ANCHOR_MAX_OFF_BEATS from the line through its neighbours
    (up to ANCHOR_NEIGHBOURS on each side, itself excluded); False with too few neighbours to fit a line."""
    reach = config.ANCHOR_NEIGHBOURS
    neighbours = anchors[max(0, index - reach):index] + anchors[index + 1:index + 1 + reach]
    line = fit_line(neighbours, min_points=2)
    if line is None:
        return False
    beat, onset_s = anchors[index]
    return abs(onset_s - (line.offset_s + beat * line.sec_per_beat)) > config.ANCHOR_MAX_OFF_BEATS * sec_per_beat


def _drop_off_line_anchors(anchors: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop anchors that sit off the line their neighbours make (pass 1 paired a repeated note with the wrong copy,
    and the map would bend through that pair); a second round catches neighbours whose fit the first drop changed.
    A steady speed-up stays on its neighbours' line, so it keeps its anchors."""
    for _ in range(config.ANCHOR_ROUNDS):
        overall = fit_line(anchors)
        if overall is None:
            return anchors
        kept = [a for i, a in enumerate(anchors) if not _off_line(i, anchors, overall.sec_per_beat)]
        if len(kept) == len(anchors):
            break
        anchors = kept
    return anchors


def build_time_map(expected: list[ExpectedNote], played: list[dict], pass1: list[Pair]) -> TimeMap | None:
    """The step 3 time map from pass 1's pairs; None (pass 1 stands) with fewer than MIN_FIT_PAIRS anchors or no
    rising line through them."""
    anchors = _same_midi_anchors(expected, played, pass1)
    anchors = _drop_off_line_anchors(anchors)
    fit = fit_line(anchors)
    return None if fit is None else TimeMap(anchors, fit)


def align_notes(expected: list[ExpectedNote], played: list[dict]) -> Alignment:
    """Pass 1 has no time limit; if the time map has >= 3 anchors, pass 2 limits pairs to +-1 beat of the map's
    time and takes off each pair's score in proportion to its distance in time, so closer pairings win ties."""
    pass1 = needleman_wunsch(expected, played)
    time_map = build_time_map(expected, played, pass1)
    if time_map is None:
        logger.info("alignment: no usable time map from pass 1's same-midi pairs; pass 1 stands")
        return Alignment(pairs=pass1, fit=None)
    sec_per_beat = time_map.fit.sec_per_beat

    def time_penalty(note: ExpectedNote, played_note: dict) -> float | None:
        distance_beats = abs(played_note["onset_s"] - time_map.time_at(note.onset_beats)) / sec_per_beat
        if distance_beats > config.PASS2_WINDOW_BEATS:
            return None
        return config.PASS2_TIME_PENALTY * min(1.0, distance_beats)

    return Alignment(pairs=needleman_wunsch(expected, played, time_penalty), fit=time_map.fit)


def build_grid(
    expected: list[ExpectedNote],
    played: list[dict],
    alignment: Alignment,
    downbeat_s: float | None,
    target_bpm: float,
) -> dict:
    """Metronome grid when the downbeat is known; otherwise the fitted one.

    Without a fit (too few pairs) the fitted grid falls back to the target tempo, anchored at the median
    offset of the pass-1 pairs (or the first played onset, or 0).
    """
    target_sec_per_beat = 60.0 / target_bpm
    if downbeat_s is not None:
        return {
            "kind": config.GRID_METRONOME,
            "offset_s": downbeat_s,
            "sec_per_beat": target_sec_per_beat,
        }
    if alignment.fit is not None:
        return {
            "kind": config.GRID_FITTED,
            "offset_s": alignment.fit.offset_s,
            "sec_per_beat": alignment.fit.sec_per_beat,
        }
    offsets = [played[p]["onset_s"] - expected[e].onset_beats * target_sec_per_beat for e, p in alignment.pairs]
    anchor = median(offsets) if offsets else (played[0]["onset_s"] if played else 0.0)
    return {"kind": config.GRID_FITTED, "offset_s": anchor, "sec_per_beat": target_sec_per_beat}
