"""LLD-3 r4-D: after POST /transposition reruns a take, its feedback is rebuilt from the new diagnosis (BE-18)."""
import pytest

import app.diagnosis
from app import store
from app.agents import run
from app.diagnosis import rerun
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


def finished_take_with_feedback(client):
    """A trumpet take played 4 semitones low with one wrong note, diagnosed (-4 detected), with feedback, status done."""
    session_id = trumpet_session()
    midis = [m - 4 for m in TUNE_MIDIS]
    midis[WRONG_NOTE_INDEX] += 1
    take_id = add_transcribed_take(session_id, perfect_played(midis))
    app.diagnosis.run(session_id, take_id)
    assert store.get(session_id).transposition["semitones"] == -4
    assert client.post(feedback_url(session_id)).status_code == 200
    update_take(session_id, take_id, status="done")
    return session_id, take_id


def set_transposition(client, session_id):
    assert client.post(f"/sessions/{session_id}/transposition", json={"semitones": NEW_SEMITONES}).status_code == 200


def test_feedback_cites_the_new_problems_after_a_transposition_rerun(client, sessions_root):
    session_id, take_id = finished_take_with_feedback(client)
    before = client.get(feedback_url(session_id)).json()
    assert before["tier1"], "the first diagnosis should give the feedback a tier-1 sentence"

    set_transposition(client, session_id)

    new_problem_ids = {problem["id"] for problem in get_take(session_id, take_id)["diagnosis"]["problems"]}
    after = client.get(feedback_url(session_id)).json()
    assert after["id"] != before["id"], "feedback was not rebuilt after the rerun"
    assert {item["problem_id"] for item in after["tier1"]} <= new_problem_ids
    assert [item["text"] for item in after["tier1"]] != [item["text"] for item in before["tier1"]]


def test_a_failing_feedback_rebuild_keeps_the_new_diagnosis_and_the_old_feedback(client, sessions_root, monkeypatch, caplog):
    session_id, take_id = finished_take_with_feedback(client)
    old_id = client.get(feedback_url(session_id)).json()["id"]

    def broken(*args):
        raise RuntimeError("agents down")

    monkeypatch.setattr(rerun, "give_take_feedback", broken)
    set_transposition(client, session_id)

    take = get_take(session_id, take_id)
    assert (take["diagnosis"]["transposition"]["semitones"], take["status"]) == (NEW_SEMITONES, "done")
    assert client.get(feedback_url(session_id)).json()["id"] == old_id
    assert f"Feedback rebuild after the diagnosis rerun failed for take {session_id}/{take_id}" in caplog.text


def test_no_feedback_is_built_for_a_take_that_is_not_done(client, sessions_root, monkeypatch):
    session_id, take_id = finished_take_with_feedback(client)
    update_take(session_id, take_id, status="diagnosed")
    calls = []
    monkeypatch.setattr(rerun, "give_take_feedback", lambda *args: calls.append(args))

    set_transposition(client, session_id)

    assert calls == []
