"""Deletes the session folders a stress run created, and only those."""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger("stress.cleanup")


def delete_sessions(sessions_dir: Path, session_ids: list[str]) -> int:
    """Remove sessions_dir/<id> for each id this run created; log each failure and return how many were removed."""
    removed = 0
    root = sessions_dir.resolve()
    for session_id in session_ids:
        folder = (root / session_id).resolve()
        if folder.parent != root:
            logger.error("Not deleting %r: it is not a direct child of %s", session_id, root)
            continue
        if not folder.is_dir():
            continue
        try:
            shutil.rmtree(folder)
            removed += 1
        except OSError:
            logger.exception("Could not delete session folder %s; remove it by hand", folder)
    return removed
