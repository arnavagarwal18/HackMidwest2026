"""What the referee hands back, and the shapes of its parts."""
from dataclasses import dataclass, field
from typing import TypedDict

from app.score.compare import CompareResult
from app.score.model import Score


class BarCheck(TypedDict):
    length_ok: bool
    range_ok: bool
    key_ok: bool
    beats: float
    expected_beats: float


class Ruling(TypedDict):
    bar: int
    pick: str  # 'homr', 'reader' or 'neither'
    why: str
    confidence: float
    accepted: bool
    rejected_because: str | None


class RefereeReport(TypedDict):
    status: str  # 'done', 'skipped' or 'failed'
    reason: str | None
    rulings: list[Ruling]
    model_id: str | None
    elapsed_ms: int


@dataclass
class RefereeResult:
    score: Score
    compare: CompareResult
    referee: RefereeReport = field(default_factory=dict)  # type: ignore[assignment]
