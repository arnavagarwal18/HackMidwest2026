"""Turn an uploaded file or built-in piece into score.json plus MusicXML in a session folder."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from music21 import converter

from app.score.builtins import builtin_path
from app.score.model import Score
from app.score.parse import MIDI_SUFFIXES, MUSICXML_SUFFIXES, parse_score_file

logger = logging.getLogger(__name__)

SOURCE_STEM = "score_source"
MUSICXML_FILENAME = "score.musicxml"
UPLOAD_SUFFIXES = tuple(sorted(MUSICXML_SUFFIXES | MIDI_SUFFIXES))
PLAIN_MUSICXML_SUFFIXES = {".xml", ".musicxml"}


def read_musicxml(folder: Path) -> str:
    path = folder / MUSICXML_FILENAME
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("Could not read %s", path)
        raise


def ingest_upload(folder: Path, filename: str, data: bytes) -> Score:
    """Parse an uploaded file and save it as the session's scanned score.

    Raises BadScoreFile (nothing saved) if it can't be parsed, OSError if the folder can't be written.
    """
    suffix = Path(filename).suffix.lower()
    with tempfile.TemporaryDirectory() as temp:
        upload = Path(temp) / f"upload{suffix}"
        upload.write_bytes(data)
        score = parse_score_file(upload)
        musicxml = data if suffix in PLAIN_MUSICXML_SUFFIXES else _export_musicxml(upload, Path(temp))
    _save_files(folder, score, musicxml, source=None if suffix in PLAIN_MUSICXML_SUFFIXES else (suffix, data))
    return score


def ingest_builtin(folder: Path, piece_id: str) -> Score:
    """Load a built-in piece as the session's scanned score; raises BuiltinNotFound for an unknown id."""
    path = builtin_path(piece_id)
    score = parse_score_file(path)
    _save_files(folder, score, path.read_bytes(), source=None)
    return score


def ingest_musicxml_file(folder: Path, path: Path) -> Score:
    """Parse a MusicXML file on disk (such as homr's output) and save it as the session's scanned score.

    Raises NoNotes or BadScoreFile (nothing saved) if it can't be used, OSError if it can't be read or saved.
    """
    score = parse_score_file(path)
    _save_files(folder, score, path.read_bytes(), source=None)
    return score


def _export_musicxml(path: Path, temp: Path) -> bytes:
    target = temp / "export.musicxml"
    converter.parse(str(path)).write("musicxml", fp=str(target))
    return target.read_bytes()


def _save_files(folder: Path, score: Score, musicxml: bytes, source: tuple[str, bytes] | None) -> None:
    """Write the original upload (if not plain MusicXML), the MusicXML and score.json, replacing any earlier ones."""
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{SOURCE_STEM}.*"):
        old.unlink()
    if source is not None:
        suffix, data = source
        (folder / f"{SOURCE_STEM}{suffix}").write_bytes(data)
    (folder / MUSICXML_FILENAME).write_bytes(musicxml)
    score.save(folder)
