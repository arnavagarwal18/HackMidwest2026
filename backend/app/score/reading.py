"""The reader agent's answer: what a vision model read from a picture of a score, bar by bar."""
from pydantic import BaseModel


class ReadNote(BaseModel):
    name: str  # pitch name with octave (e.g. "E5", "Bb4") or "rest"
    length: str  # "whole", "half", "quarter", "eighth" or "16th", with "dotted" if dotted


class ReadBar(BaseModel):
    bar: int
    notes: list[ReadNote]


class Reading(BaseModel):
    bars: list[ReadBar]
