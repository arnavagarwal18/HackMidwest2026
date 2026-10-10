"""The photo scan runs the Score reader beside homr and records what compare.py makes of the two readings."""
import time

import pytest

from app.score import compare, reader_agent
from app.score.note_text import length_from_beats
from app.score.parse import parse_score_file
from app.score.reading import ReadBar, ReadNote, Reading
from tests.test_score_photo import (  # noqa: F401  (fixtures and helpers shared with the photo tests)
    ODE_TO_JOY,
    post_photo,
    session_id,
    status,
    stub_homr,
    wait_until_done,
)


def ode_reading(changes=None) -> Reading:
    """What a perfect reader would read from the ode_to_joy photo; `changes` maps bar number -> replacement notes."""
    changes = changes or {}
    bars = []
    for bar in parse_score_file(ODE_TO_JOY).bars:
        notes = changes.get(bar.bar) or [(n.name, length_from_beats(n.dur_beats)) for n in bar.notes]
        bars.append(ReadBar(bar=bar.bar, notes=[ReadNote(name=name, length=length) for name, length in notes]))
    return Reading(bars=bars)


@pytest.fixture
def reader(monkeypatch):
    """Choose what the stubbed Score reader returns (a Reading or None); `delay` makes it slow."""
    def choose(reading, delay=0.0):
        def read_score(image_path, timeout_s=30):
            time.sleep(delay)
            return reading
        monkeypatch.setattr(reader_agent, "read_score", read_score)
    return choose


def scan(client, session_id):
    post_photo(client, session_id)
    return wait_until_done(client, session_id)


def test_identical_reading_is_double_checked_with_no_doubtful_bars(client, session_id, stub_homr, reader):
    stub_homr("ok")
    reader(ode_reading())
    done = scan(client, session_id)
    assert done["score_status"] == "scanned"
    assert done["double_checked"] is True
    assert done["doubtful_bars"] == []
    assert compare.NO_READING_WARNING not in done["warnings"]


def test_one_changed_bar_is_doubtful_in_the_status(client, session_id, stub_homr, reader):
    stub_homr("ok")
    reader(ode_reading(changes={3: [("C5", "whole")]}))
    done = scan(client, session_id)
    assert done["score_status"] == "scanned" and done["double_checked"] is True
    assert [d["bar"] for d in done["doubtful_bars"]] == [3]
    assert done["doubtful_bars"][0]["reader_text"] == "C5 whole"
    assert status(client, session_id)["doubtful_bars"] == done["doubtful_bars"]


def test_reader_with_no_reading_still_scans_and_warns_once(client, session_id, stub_homr, reader):
    stub_homr("ok")
    reader(None)
    done = scan(client, session_id)
    assert done["score_status"] == "scanned"
    assert done["double_checked"] is False
    assert done["doubtful_bars"] == []
    assert done["warnings"].count(compare.NO_READING_WARNING) == 1


def test_reader_that_crashes_does_not_fail_the_scan(client, session_id, stub_homr, monkeypatch):
    def crash(image_path, timeout_s=30):
        raise RuntimeError("reader blew up")
    stub_homr("ok")
    monkeypatch.setattr(reader_agent, "read_score", crash)
    done = scan(client, session_id)
    assert (done["score_status"], done["double_checked"]) == ("scanned", False)
    assert done["warnings"].count(compare.NO_READING_WARNING) == 1


def test_homr_failure_fails_the_scan_even_when_the_reader_is_fine(client, session_id, stub_homr, reader):
    stub_homr("fail")
    reader(ode_reading())
    done = scan(client, session_id)
    assert (done["score_status"], done["score_error"]) == ("failed", "scan_failed")
    assert done["doubtful_bars"] == [] and done["double_checked"] is False


def test_homr_failure_does_not_wait_for_a_slow_reader(client, session_id, stub_homr, reader):
    stub_homr("fail")
    reader(ode_reading(), delay=3)
    started = time.time()
    done = scan(client, session_id)
    assert done["score_status"] == "failed"
    assert time.time() - started < 2.5


def test_homr_and_the_reader_run_at_the_same_time(client, session_id, stub_homr, reader, monkeypatch):
    stub_homr("slow")  # the stub homr takes about 1 s
    reader(ode_reading(), delay=1)
    started = time.time()
    done = scan(client, session_id)
    assert done["score_status"] == "scanned" and done["double_checked"] is True
    assert time.time() - started < 1.9
