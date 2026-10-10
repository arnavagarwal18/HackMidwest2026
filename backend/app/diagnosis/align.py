"""Step 3: line up expected notes with played notes (two Needleman-Wunsch passes) and pick a time grid."""
import logging
from dataclasses import dataclass
from statistics import median
from typing import Callable

from . import config
from .expected import ExpectedNote

logger = logging.getLogger("app.diagnosis")

Pair = tuple[int, int]  # (index into expected, index into played), both in time order
PairAllowed = Callable[[ExpectedNote, dict], bool]


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
    expected: list[ExpectedNote], played: list[dict], allowed: PairAllowed | None = None
) -> list[Pair]:
    """Best global alignment; a pair is only formed where `allowed` says so (default: anywhere).

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
        if allowed is not None and not allowed(expected[i], played[j]):
            return None
        return table[i + 1][j + 1] + _pair_score(expected[i], played[j])

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


def align_notes(expected: list[ExpectedNote], played: list[dict]) -> Alignment:
    """Pass 1 has no time limit; if >= 3 same-midi pairs give a fit, pass 2 limits pairs to +-1 beat of it."""
    pass1 = needleman_wunsch(expected, played)
    same_midi = [
        (expected[e].onset_beats, played[p]["onset_s"])
        for e, p in pass1
        if expected[e].midi == played[p]["midi"]
    ]
    fit = fit_line(same_midi)
    if fit is None:
        logger.info("alignment: no usable fit from %d same-midi pairs; pass 1 stands", len(same_midi))
        return Alignment(pairs=pass1, fit=None)

    def within_window(note: ExpectedNote, played_note: dict) -> bool:
        fitted_s = fit.offset_s + note.onset_beats * fit.sec_per_beat
        return abs(played_note["onset_s"] - fitted_s) <= config.PASS2_WINDOW_BEATS * fit.sec_per_beat

    return Alignment(pairs=needleman_wunsch(expected, played, within_window), fit=fit)


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
