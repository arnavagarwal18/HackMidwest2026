"""Step 6: turn per-frame verdicts for one rule into episodes (runs of bad frames)."""
from dataclasses import dataclass
from statistics import mean, median

from . import config

TIME_TOLERANCE_S = 1e-9  # absorbs float error in frame times such as 0.1 * 3


@dataclass(frozen=True)
class Sample:
    """One frame judged against one rule. `excess` is how far past the threshold the measure is (positive means broken), None when missing."""

    value: float | None
    excess: float | None
    visibility: float


@dataclass(frozen=True)
class Episode:
    start_s: float
    end_s: float
    peak_s: float
    value: float  # median of the measure over the run
    confidence: float


def frame_interval(times: list[float]) -> float:
    """Typical seconds between frames; a frame covers [t, t + interval)."""
    gaps = [b - a for a, b in zip(times, times[1:]) if b > a]
    return median(gaps) if gaps else 1 / config.FPS


def _bad_runs(samples: list[Sample]) -> list[list[int]]:
    """[first, last] frame index of each stretch of consecutive broken frames."""
    runs: list[list[int]] = []
    for i, sample in enumerate(samples):
        if sample.excess is None or sample.excess <= 0:
            continue
        if runs and runs[-1][1] == i - 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return runs


def _merge_close(runs: list[list[int]], times: list[float], interval: float) -> list[list[int]]:
    merged: list[list[int]] = []
    for first, last in runs:
        if merged:
            gap_s = times[first] - (times[merged[-1][1]] + interval)
            if gap_s <= config.GAP_CLOSE_S + TIME_TOLERANCE_S:
                merged[-1][1] = last
                continue
        merged.append([first, last])
    return merged


def find_episodes(times: list[float], samples: list[Sample]) -> list[Episode]:
    """Runs of broken frames, gaps up to GAP_CLOSE_S closed, kept when at least MIN_EPISODE_S long."""
    interval = frame_interval(times)
    episodes = []
    for first, last in _merge_close(_bad_runs(samples), times, interval):
        start_s, end_s = times[first], times[last] + interval
        if end_s - start_s < config.MIN_EPISODE_S - TIME_TOLERANCE_S:
            continue
        run = samples[first:last + 1]
        present = [(i, s) for i, s in enumerate(run, start=first) if s.value is not None]
        peak_i = max(present, key=lambda item: item[1].excess)[0]
        confidence = mean(s.visibility for s in run) * len(present) / len(run)
        episodes.append(Episode(start_s, end_s, times[peak_i], median(s.value for _, s in present), confidence))
    return episodes
