"""Sweep reps stuck in 'processing': their scoring was interrupted (a restart, a crash) and would block the exercise for good."""
from .scoring import STATUS_PROCESSING, interrupted_rep_result

STALE_AFTER_S = 120
FINISHED_TAKE_STATUSES = ("done", "failed")


def _is_stale(take: dict | None, now: float) -> bool:
    """A take that finished (done or failed) can no longer score its rep; one that is processing or diagnosed is live
    until it has been running for STALE_AFTER_S. A rep with no stored take, or a take with no start time, is not swept."""
    if take is None:
        return False
    if take["status"] in FINISHED_TAKE_STATUSES:
        return True
    started_at = take.get("started_at")
    return started_at is not None and now - started_at > STALE_AFTER_S


def sweep_stale_reps(progress: dict, takes: dict[str, dict], now: float) -> list[str]:
    """Mark each stale 'processing' rep failed with 'scoring interrupted', leaving the tempo ladder as it is.

    Changes `progress` in place and returns the swept rep ids. `takes` is read beforehand, as progress updates must not call the store.
    """
    swept = []
    for rep_id, rep in progress["reps"].items():
        take = takes.get(rep_id)
        if rep["status"] == STATUS_PROCESSING and _is_stale(take, now):
            progress["reps"][rep_id] = interrupted_rep_result(take, progress["exercises"].get(rep["exercise_id"]))
            swept.append(rep_id)
    return swept
