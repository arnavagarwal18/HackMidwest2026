"""The background photo scan: clean the photo, run homr and the Score reader side by side, record the result.

The reader runs in a second thread on the same cleaned photo. If homr succeeds, the scan waits for the reader and
compare.py turns its reading into doubtful_bars, double_checked and warnings. A reader that fails or times out
never fails the scan: it just means "not double-checked". If homr fails, the scan fails whatever the reader says.

Then the referee (app.score.referee) settles the doubtful bars it can; it never raises, and when it is skipped or
fails the score and comparison come back as they were. Its report is saved as the session's `referee`.

Each part writes through store.update(session_id, key, value). Status is written last so a poller never sees
'scanned' before the other fields are in place.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

from app import store
from app.errors import AppError
from app.score import clean, homr_runner, reader_agent, referee
from app.score.compare import CompareResult, compare_bars
from app.score.exceptions import ScanError
from app.score.model import Score
from app.score.reading import Reading

logger = logging.getLogger(__name__)

READER_WAIT_S = reader_agent.DEFAULT_TIMEOUT_S + 5  # the reader's own limit, plus a margin

THREE_CHOICES = "Try a sharper, straighter photo, upload a MusicXML or MIDI file, or pick a built-in piece."
SCAN_MESSAGES = {
    "scan_failed": f"We couldn't read this photo. {THREE_CHOICES}",
    "scan_timeout": f"Reading the photo took too long. {THREE_CHOICES}",
    "no_notes": "No notes found in this photo. Is the whole staff inside the crop?",
}


def start_scan(session_id: str, photo: Path) -> threading.Thread:
    """Start the scan of `photo` in a background thread; the caller has already set score_status to 'scanning'."""
    thread = threading.Thread(target=run_scan, args=(session_id, photo), name=f"scan-{session_id}", daemon=True)
    thread.start()
    return thread


def run_scan(session_id: str, photo: Path) -> None:
    """Never raises: any failure ends as score_status 'failed' with a score_error code."""
    reader = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"reader-{session_id}")
    try:
        folder = store.session_dir(session_id)
        cleaned = clean.clean_photo(photo, folder / clean.CLEANED_FILENAME)
        reading_future = reader.submit(_run_reader, cleaned)
        score = homr_runner.run_homr(cleaned, folder)
        _record_success(session_id, folder, score, _await_reading(reading_future), cleaned)
    except ScanError as exc:
        logger.error("Scan of session %s failed (%s): %s", session_id, exc.code, exc)
        _record_failure(session_id, exc.code)
    except Exception:
        logger.exception("Scan of session %s crashed", session_id)
        _record_failure(session_id, "scan_failed")
    finally:
        reader.shutdown(wait=False)  # a failed scan does not wait for the reader


def _run_reader(cleaned_png: Path) -> Reading | None:
    """Run the Score reader; None means 'no reading', and the scan carries on without a double-check."""
    try:
        return reader_agent.read_score(cleaned_png)
    except Exception:
        logger.exception("Score reader crashed on %s, so there is no reading", cleaned_png)
        return None


def _await_reading(reading_future: Future) -> Reading | None:
    try:
        return reading_future.result(timeout=READER_WAIT_S)
    except FutureTimeoutError:
        logger.error("Score reader gave no answer within %s s, so there is no reading", READER_WAIT_S)
        return None


def _compare(score: Score, reading: Reading | None) -> CompareResult:
    """compare_bars, but a comparison that crashes counts as 'no reading': the scan itself is still good."""
    try:
        return compare_bars(score, reading)
    except Exception:
        logger.exception("Comparing the two readings crashed, so the scan is not double-checked")
        return compare_bars(score, None)


def _record_success(session_id: str, folder: Path, score: Score, reading: Reading | None, cleaned: Path) -> None:
    comparison = _compare(score, reading)
    refereed = referee.run(score, reading, comparison, cleaned)  # never raises; with no reading there is nothing to referee
    score, comparison = refereed.score, refereed.compare
    score.warnings.extend(comparison.warnings)
    score.save(folder)
    store.update(session_id, "score_error", None)
    store.update(session_id, "doubtful_bars", comparison.doubtful_bars)
    store.update(session_id, "double_checked", comparison.double_checked)
    store.update(session_id, "referee", refereed.referee)
    store.update(session_id, "score_status", "scanned")


def _record_failure(session_id: str, code: str) -> None:
    try:
        store.update(session_id, "score_error", code)
        store.update(session_id, "score_status", "failed")
    except (AppError, OSError):
        logger.exception("Could not record the failed scan of session %s", session_id)
