"""Run homr (optical music recognition, PyPI package `homr` 0.7.0) on a cleaned photo.

Command, run with the same Python that runs the app (so the venv's homr is used):

    python -m homr.main <folder>/cleaned.png

homr writes its MusicXML next to the image, as `<folder>/cleaned.musicxml`, and exits non-zero when it fails.
On the first run it downloads its ONNX models (about 110 MB); `homr --init` fetches them ahead of time.
The process is killed after HOMR_TIMEOUT_SECONDS (default 300). The result is parsed with parse.py and saved
as the session's score.musicxml and score.json.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from app.score import ingest
from app.score.exceptions import BadScoreFile, NoNotes, ScanError
from app.score.model import Score

logger = logging.getLogger(__name__)

TIMEOUT_ENV = "HOMR_TIMEOUT_SECONDS"
DEFAULT_TIMEOUT_SECONDS = 300.0
LOG_TAIL_CHARS = 2000


def timeout_seconds() -> float:
    raw = os.environ.get(TIMEOUT_ENV)
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    if value <= 0:
        logger.error("Ignoring %s=%r: it must be a positive number of seconds", TIMEOUT_ENV, raw)
        return DEFAULT_TIMEOUT_SECONDS
    return value


def homr_command(image: Path) -> list[str]:
    return [sys.executable, "-m", "homr.main", str(image)]


def run_homr(cleaned_png: Path, folder: Path) -> Score:
    """Read the cleaned photo with homr and save the score in `folder`.

    Raises ScanError with code scan_failed, scan_timeout or no_notes.
    """
    musicxml = cleaned_png.with_suffix(".musicxml")
    musicxml.unlink(missing_ok=True)
    _run_process(homr_command(cleaned_png), timeout_seconds())
    if not musicxml.is_file():
        raise ScanError("scan_failed", f"homr finished but wrote no {musicxml.name}")
    try:
        return ingest.ingest_musicxml_file(folder, musicxml)
    except NoNotes as exc:
        raise ScanError("no_notes", str(exc)) from exc
    except BadScoreFile as exc:
        raise ScanError("scan_failed", f"homr's MusicXML could not be read: {exc}") from exc
    except OSError as exc:
        logger.exception("Could not save the scanned score in %s", folder)
        raise ScanError("scan_failed", f"Could not save the scanned score: {exc}") from exc


def _run_process(command: list[str], timeout: float) -> None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:  # subprocess.run kills the child before raising
        logger.error("homr ran longer than %s s and was killed", timeout)
        raise ScanError("scan_timeout", f"homr ran longer than {timeout:g} seconds") from exc
    except OSError as exc:
        logger.exception("Could not start homr: %s", command)
        raise ScanError("scan_failed", f"Could not start homr: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or result.stdout)[-LOG_TAIL_CHARS:]
        logger.error("homr exited with code %s: %s", result.returncode, tail)
        raise ScanError("scan_failed", f"homr exited with code {result.returncode}")
