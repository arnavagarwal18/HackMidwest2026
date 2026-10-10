"""The trace of one feedback run: what each agent did and when, saved as {feedback_id}_trace.json."""
import json
import logging
import time
from pathlib import Path

log = logging.getLogger(__name__)

AGENTS = ("orchestrator", "coach", "planner", "checker")
DETAIL_MAX_CHARS = 500


class Trace:
    def __init__(self) -> None:
        self._started = time.monotonic()
        self.events: list[dict] = []

    def elapsed_ms(self) -> int:
        return round((time.monotonic() - self._started) * 1000)

    def add(self, agent: str, event: str, name: str, detail: str = "", duration_ms: int = 0) -> None:
        self.events.append({"t_ms": self.elapsed_ms(), "agent": agent, "event": event, "name": name,
                            "detail": detail[:DETAIL_MAX_CHARS], "duration_ms": duration_ms})

    def save(self, path: Path) -> bool:
        """Write the events to `path`; a failure is logged and returns False, since a lost trace must not lose the feedback."""
        try:
            path.write_text(json.dumps(self.events, indent=2), encoding="utf-8")
            return True
        except OSError:
            log.exception("Could not write the trace to %s", path)
            return False
