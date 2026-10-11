"""What one feedback run's agents hand back: accepted outputs, what the Checker dropped, and the check counts."""
import json
from dataclasses import dataclass, field


def describe_rejections(agent: str, tries: int, item_name: str, result: dict) -> list[str]:
    """One line per Checker problem of a rejected submit: who, which try, which item, the reason and the claim it was about."""
    lines = []
    for problem in result["problems"]:
        where = f"{item_name} {problem['index']}" if problem["index"] is not None else "whole submission"
        claim = f" [claim {json.dumps(problem['claim'], default=str)}]" if problem["claim"] is not None else ""
        lines.append(f"{agent} try {tries}, {where}: {problem['reason']}{claim}")
    return lines


@dataclass
class RunHolder:
    """Filled in by the CheckerHook and the Orchestrator's agent tools while a run is in progress."""

    feedback: dict | None = None  # the accepted CoachOutput { sentences, problem_ids }
    dropped: list[dict] = field(default_factory=list)  # [{ text, reasons }] for sentences the Checker removed
    coach_tries: int = 0
    claims_checked: int = 0
    claims_failed: int = 0
    plan: dict | None = None  # the accepted PlannerOutput { exercises }
    plan_dropped: list[dict] = field(default_factory=list)  # [{ text, reasons }] for exercises the Checker removed
    planner_tries: int = 0
    plan_claims_checked: int = 0
    plan_claims_failed: int = 0
    errors: list[Exception] = field(default_factory=list)  # exceptions raised inside the Coach tool
    planner_errors: list[Exception] = field(default_factory=list)  # exceptions raised inside the Planner tool
    rejections: list[str] = field(default_factory=list)  # every problem the Checker found in the Coach's and Planner's submits

    def note_feedback_check(self, tries: int, result: dict) -> None:
        """Record the latest Checker result for the Coach's submit number `tries`."""
        self.coach_tries = tries
        self.claims_checked = result["claims_checked"]
        self.claims_failed = result["claims_failed"]
        self.rejections += describe_rejections("coach", tries, "sentence", result)

    def note_plan_check(self, tries: int, result: dict) -> None:
        """Record the latest Checker result for the Planner's submit number `tries`."""
        self.planner_tries = tries
        self.plan_claims_checked = result["claims_checked"]
        self.plan_claims_failed = result["claims_failed"]
        self.rejections += describe_rejections("planner", tries, "exercise", result)

    def accept_feedback(self, output: dict, dropped: list[dict]) -> None:
        self.feedback = output
        self.dropped = dropped

    def accept_plan(self, output: dict, dropped: list[dict]) -> None:
        self.plan = output
        self.plan_dropped = dropped

    def check_counts(self) -> dict:
        return {"coach_tries": self.coach_tries, "planner_tries": self.planner_tries,
                "claims_checked": self.claims_checked + self.plan_claims_checked,
                "claims_failed": self.claims_failed + self.plan_claims_failed,
                "sentences_dropped": len(self.dropped)}


@dataclass
class ReplyHolder:
    """Filled in by the CheckerHook while the Instructor answers one chat message."""

    reply: dict | None = None  # the accepted { sentences }
    dropped: list[dict] = field(default_factory=list)  # [{ text, reasons }] for sentences the Checker removed
    tries: int = 0
    claims_checked: int = 0
    claims_failed: int = 0

    def note_check(self, tries: int, result: dict) -> None:
        """Record the latest Checker result for the Instructor's submit number `tries`."""
        self.tries = tries
        self.claims_checked = result["claims_checked"]
        self.claims_failed = result["claims_failed"]

    def accept(self, output: dict, dropped: list[dict]) -> None:
        self.reply = output
        self.dropped = dropped
