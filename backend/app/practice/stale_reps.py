"""Sweep reps stuck in 'processing': their scoring was interrupted (a restart, a crash) and would block the exercise for good."""
import logging
from pathlib import Path

from .scoring import STATUS_PROCESSING, interrupted_rep_result

logger = logging.getLogger("app.practice.stale_reps")

STALE_AFTER_S = 120
FINISHED_TAKE_STATUSES = ("done", "failed")


def _started_at(take: dict, folder: Path | None) -> float | None:
    """When the rep's take began: its own `started_at`, else the mtime of its uploaded file (written when the rep was
    uploaded, so it stands in for reps stored before `started_at` existed). A take whose file is gone can't be live,
    so it is dated as infinitely old; None only when the take names no file at all."""
    if take.get("started_at") is not None:
        return take["started_at"]
    if folder is None or not take.get("file"):
        return None
    try:
        return (folder / take["file"]).stat().st_mtime
    except OSError:
        logger.warning("Take %s has no start time and its file %s can't be read: counting it as stale", take.get("take_id"), take["file"])
        return float("-inf")


def _is_stale(take: dict | None, folder: Path | None, now: float) -> bool:
    """A take that finished (done or failed) can no longer score its rep; any other take is live until its rep is
    STALE_AFTER_S old, whatever state it is in. A rep with no stored take, or whose age can't be known, is not swept."""
    if take is None:
        return False
    if take["status"] in FINISHED_TAKE_STATUSES:
        return True
    started_at = _started_at(take, folder)
    return started_at is not None and now - started_at > STALE_AFTER_S


def sweep_stale_reps(progress: dict, takes: dict[str, dict], now: float, folder: Path | None = None) -> list[str]:
    """Mark each stale 'processing' rep failed with 'scoring interrupted', leaving the tempo ladder as it is.

    Changes `progress` in place and returns the swept rep ids. `takes` is read beforehand, as progress updates must not call the store. `folder` is the session's folder,
    where a take with no `started_at` is dated by its file.
    """
    swept = []
    for rep_id, rep in progress["reps"].items():
        take = takes.get(rep_id)
        if rep["status"] == STATUS_PROCESSING and _is_stale(take, folder, now):
            progress["reps"][rep_id] = interrupted_rep_result(take, progress["exercises"].get(rep["exercise_id"]))
            swept.append(rep_id)
    return swept
