"""The result shape shared by the feedback and plan checks."""
import logging
from contextlib import contextmanager
from typing import Iterator, Optional

log = logging.getLogger(__name__)


class Report:
    """Collects Checker problems and counts the claims that were examined."""

    def __init__(self) -> None:
        self.problems: list[dict] = []
        self.claims_checked = 0

    def add(self, index: Optional[int], reason: str, claim: Optional[dict] = None) -> None:
        self.problems.append({"index": index, "claim": claim, "reason": reason})

    @contextmanager
    def guard(self, index: Optional[int], kind: str) -> Iterator[None]:
        """Turn an unexpected failure while checking one item into a rejection, never a crash."""
        try:
            yield
        except Exception as exc:
            log.exception("checking %s %s failed on malformed output", kind, index)
            self.add(index, f"bad {kind}: could not be checked ({type(exc).__name__}); check the field types")

    def as_result(self) -> dict:
        return {
            "ok": not self.problems,
            "problems": self.problems,
            "claims_checked": self.claims_checked,
            "claims_failed": sum(1 for p in self.problems if p["claim"] is not None),
        }
