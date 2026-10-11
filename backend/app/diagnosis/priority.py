"""The order problems matter in: wrong / missed notes, then rushing / dragging, then everything else (form flags, small timing slips) by score.

One key shared by the ranking, the fallback and the agents' tools, so the AI and the rule-based path agree.
"""
from . import config

PRIORITY_GROUPS = {
    config.PROBLEM_NOTES: 0,
    config.DRIFT_RUSHING: 1,
    config.DRIFT_DRAGGING: 1,
    config.PROBLEM_FORM: 2,
    config.TIMING_LATE: 2,
    config.TIMING_EARLY: 2,
}
LAST_GROUP = 3  # a kind this table doesn't know (e.g. the tier-3 range note) goes last


def priority_key(problem: dict) -> tuple:
    """Sort key, most important first: kind group, then higher score, then earlier in the take."""
    group = PRIORITY_GROUPS.get(problem.get("kind"), LAST_GROUP)
    return (group, -problem.get("score", 0), problem.get("first_time_s", 0))
