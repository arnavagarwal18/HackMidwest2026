"""Latency samples and the per-route summary numbers."""
import statistics
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Sample:
    route: str
    status: int | None  # None when no response arrived (timeout or connection error)
    latency_s: float
    error: str | None = None


@dataclass
class Recorder:
    samples: list[Sample] = field(default_factory=list)

    def add(self, sample: Sample) -> None:
        self.samples.append(sample)

    def routes(self) -> list[str]:
        return list(dict.fromkeys(s.route for s in self.samples))


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def summarize(samples: list[Sample], wall_s: float) -> dict:
    """p50/p95/max latency in ms, status counts, and requests per second over the wall time."""
    latencies = [s.latency_s for s in samples]
    statuses = Counter(str(s.status) if s.status is not None else (s.error or "no-response") for s in samples)
    return {
        "requests": len(samples),
        "p50_ms": round(statistics.median(latencies) * 1000, 1),
        "p95_ms": round(percentile(latencies, 0.95) * 1000, 1),
        "max_ms": round(max(latencies) * 1000, 1),
        "statuses": dict(sorted(statuses.items())),
        "throughput_rps": round(len(samples) / wall_s, 1) if wall_s > 0 else None,
    }
