"""The stale-rep sweep: a rep stuck in 'processing' is failed when a new rep is claimed, so it can't block the exercise."""
import os
import time

import pytest

from app import store
from app.practice import init_plan, rep_routes
from app.practice.progress import read_progress, update_progress
from app.practice.scoring import processing_rep_result
from app.practice.stale_reps import STALE_AFTER_S, sweep_stale_reps
from tests.practice_helpers import add_rep, exercise, save_plan
from tests.test_sessions import assert_error

STUCK_ID = "t1"
LADDER = {"current_bpm": 64, "streak": 1, "fails_in_row": 1, "best_passed_bpm": 60}
INTERRUPTED = ["scoring interrupted"]


@pytest.fixture
def session_id(sessions_root):
    sid = store.create("trumpet").session_id
    save_plan(sid, "pl1", exercise("ex1", 2, 3, start_bpm=60))
    init_plan(sid, "pl1")
    update_progress(sid, lambda p: p["exercises"]["ex1"].update(LADDER))
    return sid


@pytest.fixture
def started(monkeypatch):
    started = []
    monkeypatch.setattr(rep_routes, "start_pipeline", lambda session_id, take_id: started.append(take_id))
    return started


def stick_a_rep(session_id: str, take_status: str, age_s: float | None = 5, file_age_s: float | None = None) -> None:
    """A rep whose RepResult is 'processing' and whose take is in `take_status`, started `age_s` seconds ago (None: no start
    time). With `file_age_s`, the take also has its uploaded file, last written that many seconds ago."""
    started_at = {} if age_s is None else {"started_at": time.time() - age_s}
    file_name = {} if file_age_s is None else {"file": "t1.wav"}
    take = add_rep(session_id, STUCK_ID, tempo_bpm=64.0, status=take_status, **started_at, **file_name)
    if file_age_s is not None:
        uploaded = store.session_dir(session_id) / "t1.wav"
        uploaded.write_bytes(b"RIFFdata")
        os.utime(uploaded, (time.time() - file_age_s,) * 2)

    def claim(progress: dict) -> None:
        progress["reps"][STUCK_ID] = processing_rep_result(take)
        progress["exercises"]["ex1"]["rep_ids"].append(STUCK_ID)

    update_progress(session_id, claim)


def post_rep(client, session_id: str):
    return client.post(f"/sessions/{session_id}/exercises/ex1/reps", data={"kind": "mic", "source": "recorded", "downbeat_s": "0.5"},
                       files={"file": ("rep.wav", b"RIFFdata", "audio/wav")})


def assert_swept_with_ladder_unchanged(session_id: str) -> None:
    progress = read_progress(session_id)
    rep = progress["reps"][STUCK_ID]
    assert (rep["status"], rep["reasons"], rep["passed"]) == ("failed", INTERRUPTED, None)
    assert (rep["next_bpm"], rep["streak"], rep["exercise_complete"]) == (64, 1, False)
    assert {key: progress["exercises"]["ex1"][key] for key in LADDER} == LADDER


@pytest.mark.parametrize("take_status", ["done", "failed"])
def test_a_rep_whose_take_is_finished_is_swept_and_the_new_rep_is_accepted(client, session_id, started, take_status):
    stick_a_rep(session_id, take_status)
    response = post_rep(client, session_id)
    assert response.status_code == 202, response.text
    assert response.json()["rep_id"] == "t2"
    assert_swept_with_ladder_unchanged(session_id)
    assert read_progress(session_id)["reps"]["t2"]["status"] == "processing"
    assert read_progress(session_id)["exercises"]["ex1"]["rep_ids"] == [STUCK_ID, "t2"]
    assert started == ["t2"]


@pytest.mark.parametrize("take_status", ["processing", "diagnosed"])
def test_a_rep_older_than_the_limit_is_swept_even_when_its_take_looks_live(client, session_id, started, take_status):
    stick_a_rep(session_id, take_status, age_s=STALE_AFTER_S + 1)
    assert post_rep(client, session_id).status_code == 202
    assert_swept_with_ladder_unchanged(session_id)


@pytest.mark.parametrize("take_status", ["processing", "diagnosed"])
def test_a_rep_whose_take_is_live_is_not_swept(client, session_id, started, take_status):
    stick_a_rep(session_id, take_status, age_s=STALE_AFTER_S - 30)
    assert_error(post_rep(client, session_id), 409, "wrong_state")
    progress = read_progress(session_id)
    assert progress["reps"][STUCK_ID]["status"] == "processing"
    assert progress["exercises"]["ex1"]["rep_ids"] == [STUCK_ID]
    assert list(store.get(session_id).takes) == [STUCK_ID]
    assert started == []


def test_a_live_take_with_no_start_time_and_no_file_is_not_swept(client, session_id, started):
    stick_a_rep(session_id, "processing", age_s=None)
    assert_error(post_rep(client, session_id), 409, "wrong_state")
    assert read_progress(session_id)["reps"][STUCK_ID]["status"] == "processing"


@pytest.mark.parametrize("take_status", ["processing", "diagnosed"])
def test_an_old_stuck_rep_with_no_start_time_is_dated_by_its_file_and_swept(client, session_id, started, take_status):
    stick_a_rep(session_id, take_status, age_s=None, file_age_s=STALE_AFTER_S + 1)
    assert post_rep(client, session_id).status_code == 202
    assert_swept_with_ladder_unchanged(session_id)
    assert started == ["t2"]


def test_a_young_live_rep_with_no_start_time_is_not_swept(client, session_id, started):
    stick_a_rep(session_id, "processing", age_s=None, file_age_s=STALE_AFTER_S - 30)
    assert_error(post_rep(client, session_id), 409, "wrong_state")
    assert read_progress(session_id)["reps"][STUCK_ID]["status"] == "processing"
    assert started == []


def test_a_processing_rep_with_no_start_time_whose_file_is_gone_is_swept(client, session_id, started, caplog):
    stick_a_rep(session_id, "processing", age_s=None, file_age_s=5)
    (store.session_dir(session_id) / "t1.wav").unlink()
    assert post_rep(client, session_id).status_code == 202
    assert_swept_with_ladder_unchanged(session_id)
    assert "counting it as stale" in caplog.text


def test_a_new_rep_take_records_when_it_started(client, session_id, started):
    before = time.time()
    assert post_rep(client, session_id).status_code == 202
    assert before <= store.get(session_id).takes["t1"]["started_at"] <= time.time()


def test_the_sweep_leaves_scored_reps_alone(session_id):
    stick_a_rep(session_id, "done")
    update_progress(session_id, lambda p: p["reps"].update({"t9": {**p["reps"][STUCK_ID], "take_id": "t9", "status": "scored"}}))
    progress = read_progress(session_id)
    swept = sweep_stale_reps(progress, store.get(session_id).takes, time.time())
    assert swept == [STUCK_ID]
    assert progress["reps"]["t9"]["status"] == "scored"
    assert progress["exercises"]["ex1"]["current_bpm"] == LADDER["current_bpm"]


def test_a_rep_with_no_stored_take_is_not_swept(session_id):
    stick_a_rep(session_id, "processing", age_s=STALE_AFTER_S + 1)
    progress = read_progress(session_id)
    assert sweep_stale_reps(progress, {}, time.time()) == []
    assert progress["reps"][STUCK_ID]["status"] == "processing"
