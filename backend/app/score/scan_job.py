"""The background photo scan: clean the photo, run homr, record the result on the session.

Each part writes through store.update(session_id, key, value). Status is written last so a poller never sees
'scanned' before the other fields are in place.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from app import store
from app.errors import AppError
from app.score import clean, homr_runner
from app.score.exceptions import ScanError
from app.score.model import Score

logger = logging.getLogger(__name__)

THREE_CHOICES = "Try a sharper, straighter photo, upload a MusicXML or MIDI file, or pick a built-in piece."
SCAN_MESSAGES = {
    "scan_failed": f"We couldn't read this photo. {THREE_CHOICES}",
    "scan_timeout": f"Reading the photo took too long. {THREE_CHOICES}",
    "no_notes": "No notes found in this photo. Is the whole staff inside the crop?",
}
NOT_DOUBLE_CHECKED_WARNING = "We couldn't double-check this scan: compare it with your copy before you confirm."


def start_scan(session_id: str, photo: Path) -> threading.Thread:
    """Start the scan of `photo` in a background thread; the caller has already set score_status to 'scanning'."""
    thread = threading.Thread(target=run_scan, args=(session_id, photo), name=f"scan-{session_id}", daemon=True)
    thread.start()
    return thread


def run_scan(session_id: str, photo: Path) -> None:
    """Never raises: any failure ends as score_status 'failed' with a score_error code."""
    try:
        folder = store.session_dir(session_id)
        cleaned = clean.clean_photo(photo, folder / clean.CLEANED_FILENAME)
        score = homr_runner.run_homr(cleaned, folder)
        _run_reader(cleaned)
        _record_success(session_id, folder, score)
    except ScanError as exc:
        logger.error("Scan of session %s failed (%s): %s", session_id, exc.code, exc)
        _record_failure(session_id, exc.code)
    except Exception:
        logger.exception("Scan of session %s crashed", session_id)
        _record_failure(session_id, "scan_failed")


def _run_reader(cleaned_png: Path) -> None:
    """HOOK for the Score reader (LLD-1 change 6): no reader yet, so there is no reading to compare with.

    Later this runs the reader on `cleaned_png` in a second thread (alongside homr) and returns its reading,
    which compare.py turns into doubtful_bars and double_checked.
    """
    return None


def _record_success(session_id: str, folder: Path, score: Score) -> None:
    score.warnings.append(NOT_DOUBLE_CHECKED_WARNING)  # until a reader result exists, see _run_reader
    score.save(folder)
    store.update(session_id, "score_error", None)
    store.update(session_id, "doubtful_bars", [])
    store.update(session_id, "double_checked", False)
    store.update(session_id, "score_status", "scanned")


def _record_failure(session_id: str, code: str) -> None:
    try:
        store.update(session_id, "score_error", code)
        store.update(session_id, "score_status", "failed")
    except (AppError, OSError):
        logger.exception("Could not record the failed scan of session %s", session_id)
