"""LLD-3 r4-D: after POST /transposition reruns a take, its feedback is rebuilt from the new diagnosis (BE-18)."""
import pytest

import app.diagnosis
from app import store
from app.agents import run
from app.takes.take_store import get_take, update_take
from test_diagnosis_transposition import TUNE_MIDIS, trumpet_session
from diagnosis_session import add_transcribed_take
from diagnosis_samples import perfect_played

WRONG_NOTE_INDEX = 5  # bar 2, second note
NEW_SEMITONES = 0


@pytest.fixture(autouse=True)
def ai_off(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: False)


def feedback_url(session_id):
    return f"/sessions/{session_id}/takes/t1/feedback"


@pytest.mark.xfail(strict=True, reason="BE-18: rerun_takes (diagnosis/rerun.py) re-diagnoses but never calls agents.run.run_feedback")
def test_feedback_cites_the_new_problems_after_a_transposition_rerun(client, sessions_root):
    session_id = trumpet_session()
    midis = [m - 4 for m in TUNE_MIDIS]
    midis[WRONG_NOTE_INDEX] += 1
    take_id = add_transcribed_take(session_id, perfect_played(midis))
    app.diagnosis.run(session_id, take_id)
    assert store.get(session_id).transposition["semitones"] == -4
    assert client.post(feedback_url(session_id)).status_code == 200
    update_take(session_id, take_id, status="done")
    before = client.get(feedback_url(session_id)).json()
    assert before["tier1"], "the first diagnosis should give the feedback a tier-1 sentence"

    assert client.post(f"/sessions/{session_id}/transposition", json={"semitones": NEW_SEMITONES}).status_code == 200

    new_problem_ids = {problem["id"] for problem in get_take(session_id, take_id)["diagnosis"]["problems"]}
    after = client.get(feedback_url(session_id)).json()
    assert after["id"] != before["id"], "feedback was not rebuilt after the rerun"
    assert {item["problem_id"] for item in after["tier1"]} <= new_problem_ids
    assert [item["text"] for item in after["tier1"]] != [item["text"] for item in before["tier1"]]
