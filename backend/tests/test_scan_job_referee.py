"""The photo scan hands its doubtful bars to the referee and serves what comes back (LLD-8 change 3).

The referee's model is always a stub agent that calls the session's tools; nothing here reaches Bedrock.
"""
import json
from functools import partial

import pytest

from app import store
from app.agents.config import ConfigError
from app.score import compare, referee, reader_agent, scan_job
from app.score.parse import parse_score_file
from app.score.referee import agent
from tests.referee_helpers import SETTINGS_OFF, SETTINGS_ON, stub_factory
from tests.test_scan_job_reader import ode_reading
from tests.test_score_photo import ODE_TO_JOY, post_photo, session_id, status, stub_homr, wait_until_done  # noqa: F401

C5_WHOLE = [("C5", "whole")]


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(agent, "get_settings", lambda: SETTINGS_ON)


@pytest.fixture
def scan_with_bar_3_doubtful(client, session_id, stub_homr, monkeypatch):
    """Run a photo scan where the reader reads bar 3 differently, with the referee's agent being `script`."""
    def run(script):
        stub_homr("ok")
        monkeypatch.setattr(reader_agent, "read_score", lambda image_path, timeout_s=30: ode_reading({3: C5_WHOLE}))
        monkeypatch.setattr(scan_job.referee, "run", partial(referee.run, agent_factory=stub_factory(script)))
        post_photo(client, session_id)
        return wait_until_done(client, session_id)
    return run


def rule_bar_3(pick, why="the photo shows it", confidence=0.9):
    return lambda session, cancel: session.submit_ruling(3, pick, why, confidence)


def bar_3_notes(client, session_id):
    score = json.loads(client.get(f"/sessions/{session_id}/score", params={"format": "json"}).text)
    return [n["name"] for n in score["bars"][2]["notes"]]


def test_the_status_route_carries_the_referee_report_and_each_bars_note(client, session_id, scan_with_bar_3_doubtful):
    done = scan_with_bar_3_doubtful(rule_bar_3("neither", "both look plausible", 0.5))
    assert done["score_status"] == "scanned" and done["double_checked"] is True
    assert done["referee"]["status"] == "done" and done["referee"]["reason"] is None
    assert done["referee"]["model_id"] == "vision-model"
    assert [(r["bar"], r["pick"], r["accepted"], r["rejected_because"]) for r in done["referee"]["rulings"]] == [
        (3, "neither", False, "neither")]
    assert [(d["bar"], d["referee_note"]) for d in done["doubtful_bars"]] == [(3, "both look plausible")]
    assert status(client, session_id)["referee"] == done["referee"]  # saved, not recomputed


def test_an_accepted_ruling_leaves_doubtful_bars_and_replaces_the_bar_in_the_score(client, session_id, scan_with_bar_3_doubtful):
    done = scan_with_bar_3_doubtful(rule_bar_3("reader"))
    assert done["referee"]["rulings"][0]["accepted"] is True
    assert done["doubtful_bars"] == [] and done["double_checked"] is True
    assert bar_3_notes(client, session_id) == ["C5"]


def test_an_accepted_homr_ruling_keeps_homrs_bar(client, session_id, scan_with_bar_3_doubtful):
    homr_notes = [n.name for n in parse_score_file(ODE_TO_JOY).bars[2].notes]
    done = scan_with_bar_3_doubtful(rule_bar_3("homr"))
    assert done["doubtful_bars"] == []
    assert bar_3_notes(client, session_id) == homr_notes


def test_a_failed_referee_keeps_the_scan_working(client, session_id, scan_with_bar_3_doubtful):
    def model_down(session, cancel):
        raise RuntimeError("bedrock is down")

    done = scan_with_bar_3_doubtful(model_down)
    assert done["score_status"] == "scanned" and done["score_error"] is None
    assert (done["referee"]["status"], done["referee"]["reason"]) == ("failed", "model_error")
    assert [(d["bar"], d["reader_text"]) for d in done["doubtful_bars"]] == [(3, "C5 whole")]
    assert "referee_note" not in done["doubtful_bars"][0]
    assert client.get(f"/sessions/{session_id}/score").status_code == 200


@pytest.mark.parametrize("ai_settings", ["off", "config_error"])
def test_with_ai_off_the_referee_is_skipped_and_the_check_step_is_as_before(
    client, session_id, scan_with_bar_3_doubtful, monkeypatch, ai_settings
):
    def ai_off():
        if ai_settings == "config_error":
            raise ConfigError("AI_ENABLED is true but a model is empty.")
        return SETTINGS_OFF

    monkeypatch.setattr(agent, "get_settings", ai_off)

    def must_not_be_called(session, cancel):
        raise AssertionError("the referee's model ran with AI off")

    done = scan_with_bar_3_doubtful(must_not_be_called)
    assert (done["referee"]["status"], done["referee"]["reason"], done["referee"]["rulings"]) == ("skipped", "ai_off", [])
    assert done["referee"]["model_id"] is None
    assert done["score_status"] == "scanned" and done["double_checked"] is True
    assert [(d["bar"], d["homr_text"], d["reader_text"]) for d in done["doubtful_bars"]] == [
        (3, done["doubtful_bars"][0]["homr_text"], "C5 whole")]
    assert "referee_note" not in done["doubtful_bars"][0]
    assert compare.NO_READING_WARNING not in done["warnings"]


def test_an_old_saved_scan_without_the_field_still_loads_and_serves(client, session_id, scan_with_bar_3_doubtful):
    scan_with_bar_3_doubtful(rule_bar_3("neither", "unsure", 0.5))
    session_file = store.session_dir(session_id) / store.SESSION_FILE
    saved = json.loads(session_file.read_text(encoding="utf-8"))
    del saved["referee"]
    session_file.write_text(json.dumps(saved), encoding="utf-8")
    store._sessions.pop(session_id)  # force a reload from disk, as after a restart

    old = status(client, session_id)
    assert old["referee"] is None
    assert old["score_status"] == "scanned" and [d["bar"] for d in old["doubtful_bars"]] == [3]
    assert client.get(f"/sessions/{session_id}/score").status_code == 200
