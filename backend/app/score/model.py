"""Score data model and its score.json (de)serialisation."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

SCORE_FILENAME = "score.json"


@dataclass
class Note:
    idx: int
    pitch_midi: int | None
    name: str
    start_beat: float
    dur_beats: float
    tied_from_previous: bool = False


@dataclass
class Bar:
    bar: int
    start_beat: float
    beats: float
    notes: list[Note] = field(default_factory=list)


@dataclass
class Score:
    title: str
    instrument: str
    tempo_bpm: float
    time_signature: tuple[int, int]
    written_transpose_semitones: int | None
    bars: list[Bar]
    warnings: list[str] = field(default_factory=list)
    key_fifths: int | None = None  # sharps (positive) or flats (negative) in the key signature; None = unknown

    def to_dict(self) -> dict:
        data = asdict(self)
        data["time_signature"] = list(self.time_signature)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> Score:
        try:
            return cls(
                title=data["title"],
                instrument=data["instrument"],
                tempo_bpm=float(data["tempo_bpm"]),
                time_signature=(int(data["time_signature"][0]), int(data["time_signature"][1])),
                written_transpose_semitones=data["written_transpose_semitones"],
                bars=[
                    Bar(
                        bar=b["bar"],
                        start_beat=b["start_beat"],
                        beats=b["beats"],
                        notes=[Note(**n) for n in b["notes"]],
                    )
                    for b in data["bars"]
                ],
                warnings=list(data["warnings"]),
                key_fifths=data.get("key_fifths"),
            )
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            raise ValueError(f"Invalid score data: {exc!r}") from exc

    @classmethod
    def from_json(cls, text: str) -> Score:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid score JSON: {exc}") from exc
        return cls.from_dict(data)

    def save(self, folder: str | Path) -> Path:
        """Write score.json into the session folder and return its path."""
        path = Path(folder) / SCORE_FILENAME
        try:
            path.write_text(self.to_json(), encoding="utf-8")
        except OSError:
            logger.exception("Could not write %s", path)
            raise
        return path

    @classmethod
    def load(cls, folder: str | Path) -> Score:
        """Read score.json from the session folder."""
        path = Path(folder) / SCORE_FILENAME
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            logger.exception("Could not read %s", path)
            raise
        return cls.from_json(text)
