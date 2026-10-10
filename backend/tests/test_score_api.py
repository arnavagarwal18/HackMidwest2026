from pathlib import Path

import pytest

from app.score.api import bar_at_beat, beats_to_seconds, get_score
from app.score.bars import RawEvent, build_bars
from app.score.exceptions import NotConfirmed
from app.score.model import Score


def make_score() -> Score:
    bars = build_bars([RawEvent(0, 4, 60, "C4"), RawEvent(4, 4, 62, "D4", True)], [(0, 4), (4, 4), (8, 3)])
    return Score("T", "Trumpet", 100.0, (4, 4), -2, bars, ["w"])


class StubStore:
    def __init__(self, status: str, folder: Path):
        self.status, self.folder = status, folder

    def score_status(self, session_id: str) -> str:
        return self.status

    def session_dir(self, session_id: str) -> Path:
        return self.folder


def test_json_round_trip():
    score = make_score()
    assert Score.from_json(score.to_json()) == score


def test_json_stores_time_signature_as_list():
    assert make_score().to_dict()["time_signature"] == [4, 4]


def test_from_json_rejects_garbage():
    with pytest.raises(ValueError, match="Invalid score JSON"):
        Score.from_json("{not json")
    with pytest.raises(ValueError, match="Invalid score data"):
        Score.from_json('{"title": "x"}')


def test_save_and_load_folder(tmp_path):
    score = make_score()
    path = score.save(tmp_path)
    assert path.name == "score.json"
    assert Score.load(tmp_path) == score


def test_get_score_returns_confirmed_score(tmp_path):
    make_score().save(tmp_path)
    assert get_score("s1", StubStore("confirmed", tmp_path)) == make_score()


@pytest.mark.parametrize("status", ["pending", "none", ""])
def test_get_score_requires_confirmation(tmp_path, status):
    make_score().save(tmp_path)
    with pytest.raises(NotConfirmed):
        get_score("s1", StubStore(status, tmp_path))


@pytest.mark.parametrize(
    "beat, expected",
    [(0, 1), (3.99, 1), (4, 2), (7.5, 2), (8, 3), (10.9, 3), (99, 3), (-1, 1)],
)
def test_bar_at_beat(beat, expected):
    assert bar_at_beat(make_score(), beat) == expected


@pytest.mark.parametrize(
    "beats, bpm, expected", [(4, 120, 2.0), (1, 60, 1.0), (0, 90, 0.0), (3, 90, 2.0)]
)
def test_beats_to_seconds(beats, bpm, expected):
    assert beats_to_seconds(beats, bpm) == pytest.approx(expected)


@pytest.mark.parametrize("bpm", [0, -10])
def test_beats_to_seconds_rejects_bad_tempo(bpm):
    with pytest.raises(ValueError, match="tempo_bpm"):
        beats_to_seconds(4, bpm)
