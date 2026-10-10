"""The result shape shared by the feedback and plan checks."""
from typing import Optional


class Report:
    """Collects Checker problems and counts the claims that were examined."""

    def __init__(self) -> None:
        self.problems: list[dict] = []
        self.claims_checked = 0

    def add(self, index: Optional[int], reason: str, claim: Optional[dict] = None) -> None:
        self.problems.append({"index": index, "claim": claim, "reason": reason})

    def as_result(self) -> dict:
        return {
            "ok": not self.problems,
            "problems": self.problems,
            "claims_checked": self.claims_checked,
            "claims_failed": sum(1 for p in self.problems if p["claim"] is not None),
        }
