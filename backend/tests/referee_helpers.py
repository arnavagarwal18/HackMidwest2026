"""Builders shared by the referee tests: a small score, a reading, their comparison, and a stub agent."""
from dataclasses import replace
from pathlib import Path

import pytest

from app.agents.config import Settings
from app.score import compare as compare_module
from app.score.model import Bar, Note, Score
from app.score.reading import ReadBar, ReadNote, Reading
from app.score.referee import agent

SETTINGS_ON = Settings(region="us-east-1", text_model="text-model", vision_model="vision-model", aws_profile="",
                       ai_enabled=True)
SETTINGS_OFF = replace(SETTINGS_ON, ai_enabled=False)
FOUR_QUARTERS = [("E5", "quarter")] * 4
LENGTH_BEATS = {"quarter": 1.0, "half": 2.0, "eighth": 0.5, "whole": 4.0}


def make_score(bars: list[list[tuple[str, str]]], time_signature=(4, 4), key_fifths=None) -> Score:
    """A score whose bar n (from 1) has the given (name, length word) notes."""
    score_bars, start = [], 0.0
    for number, notes in enumerate(bars, 1):
        built, cursor = [], start
        for idx, (name, length) in enumerate(notes):
            beats = LENGTH_BEATS[length]
            built.append(Note(idx, None if name == "rest" else 60, name, cursor, beats))
            cursor += beats
        beats_in_bar = time_signature[0] * 4 / time_signature[1]
        score_bars.append(Bar(bar=number, start_beat=start, beats=beats_in_bar, notes=built))
        start += beats_in_bar
    return Score("t", "trumpet", 90.0, time_signature, None, score_bars, key_fifths=key_fifths)


def make_reading(bars: dict[int, list[tuple[str, str]]]) -> Reading:
    return Reading(bars=[ReadBar(bar=n, notes=[ReadNote(name=a, length=b) for a, b in notes])
                         for n, notes in bars.items()])


def compare_of(score: Score, reading: Reading):
    return compare_module.compare_bars(score, reading)


def stub_factory(script):
    """An agent factory whose agent just calls script(session, cancel), as a model would call the tools."""
    def factory(settings, session, timeout_s):
        return lambda prompt, cancel: script(session, cancel)
    return factory


@pytest.fixture
def ai_on(monkeypatch):
    monkeypatch.setattr(agent, "get_settings", lambda: SETTINGS_ON)


@pytest.fixture
def photo(tmp_path) -> Path:
    path = tmp_path / "cleaned.png"
    path.write_bytes(b"\x89PNG not really")
    return path
