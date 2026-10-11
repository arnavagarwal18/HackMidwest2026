import pytest

from app import store
from app.errors import storage_error
from app.practice import init_plan
from app.practice.progress import read_progress, update_progress
from app.practice import rep_routes
from app.takes import media_tools, pipeline
from tests.practice_helpers import add_take, clean_diagnosis, exercise, save_plan
from tests.test_sessions import assert_error

REP_FIELDS = {"kind": "mic", "source": "recorded", "downbeat_s": "0.5"}


@pytest.fixture
def session_id(sessions_root):
    sid = store.create("trumpet").session_id
    save_plan(sid, "pl1", exercise("ex1", 2, 3, start_bpm=60))
    init_plan(sid, "pl1")
    return sid


@pytest.fixture
def started(monkeypatch):
    """Replace the pipeline start so an accepted rep stays 'processing'; the list holds the take ids it was started for."""
    started = []
    monkeypatch.setattr(rep_routes, "start_pipeline", lambda session_id, take_id: started.append(take_id))
    return started


def post_rep(client, session_id, exercise_id="ex1", content_type="audio/wav", content=b"RIFFdata", **overrides):
    fields = {k: v for k, v in {**REP_FIELDS, **overrides}.items() if v is not None}
    return client.post(f"/sessions/{session_id}/exercises/{exercise_id}/reps", data=fields,
                       files={"file": ("rep.wav", content, content_type)})


def assert_nothing_stored(session_id):
    assert store.get(session_id).takes == {}
    progress = read_progress(session_id)
    assert progress["reps"] == {} and progress["exercises"]["ex1"]["rep_ids"] == []
    assert [path.name for path in store.session_dir(session_id).iterdir()] == ["session.json"]


def test_a_rep_is_accepted_at_the_current_tempo_with_bars_from_the_exercise(client, session_id, started):
    update_progress(session_id, lambda p: p["exercises"]["ex1"].update(current_bpm=64))
    response = post_rep(client, session_id)
    assert response.status_code == 202
    assert response.json() == {"rep_id": "t1", "tempo_bpm": 64, "status": "processing"}
    take = store.get(session_id).takes["t1"]
    assert (take["purpose"], take["exercise_id"], take["bar_from"], take["bar_to"], take["tempo_bpm"]) == ("rep", "ex1", 2, 3, 64)
    assert (store.session_dir(session_id) / take["file"]).is_file()
    progress = read_progress(session_id)
    assert progress["exercises"]["ex1"]["rep_ids"] == ["t1"]
    assert progress["reps"]["t1"]["status"] == "processing"
    assert started == ["t1"]


def test_bars_and_tempo_in_the_request_are_ignored(client, session_id, started):
    assert post_rep(client, session_id, bar_from="1", bar_to="9", tempo_bpm="200").json()["tempo_bpm"] == 60
    take = store.get(session_id).takes["t1"]
    assert (take["bar_from"], take["bar_to"]) == (2, 3)


def test_a_second_rep_while_one_is_processing_is_refused_and_stores_nothing(client, session_id, started):
    assert post_rep(client, session_id).status_code == 202
    assert_error(post_rep(client, session_id), 409, "wrong_state")
    assert list(store.get(session_id).takes) == ["t1"]
    assert read_progress(session_id)["exercises"]["ex1"]["rep_ids"] == ["t1"]
    assert started == ["t1"]
    assert sorted(path.name for path in store.session_dir(session_id).iterdir()) == ["session.json", "t1_upload.wav"]


def test_the_409_check_and_the_processing_write_are_atomic(client, session_id, started, monkeypatch):
    assert post_rep(client, session_id).status_code == 202
    stale = {**read_progress(session_id), "reps": {}}
    stale["exercises"]["ex1"]["rep_ids"] = []
    monkeypatch.setattr(rep_routes, "read_progress", lambda session_id: stale)  # the early check sees no rep processing
    assert_error(post_rep(client, session_id), 409, "wrong_state")
    assert list(store.get(session_id).takes) == ["t1"]
    assert read_progress(session_id)["exercises"]["ex1"]["rep_ids"] == ["t1"]
    assert not [path for path in store.session_dir(session_id).iterdir() if path.name.startswith("t2")]


def test_a_new_rep_is_accepted_once_the_last_one_is_scored(client, session_id, started):
    post_rep(client, session_id)
    update_progress(session_id, lambda p: p["reps"]["t1"].update(status="scored"))
    assert post_rep(client, session_id).json()["rep_id"] == "t2"
    assert read_progress(session_id)["exercises"]["ex1"]["rep_ids"] == ["t1", "t2"]


def test_a_complete_exercise_refuses_reps(client, session_id, started):
    update_progress(session_id, lambda p: p["exercises"]["ex1"].update(complete=True))
    assert_error(post_rep(client, session_id), 409, "wrong_state")
    assert_nothing_stored(session_id)


def test_unknown_exercise_and_session_are_404(client, session_id, started):
    assert_error(post_rep(client, session_id, exercise_id="nope"), 404, "exercise_not_found")
    assert_error(post_rep(client, "0" * 32), 404, "session_not_found")
    assert_nothing_stored(session_id)


@pytest.mark.parametrize("overrides", [{"kind": "film"}, {"source": None}, {"downbeat_s": None}, {"downbeat_s": "-1"}])
def test_bad_fields_are_422_and_store_nothing(client, session_id, started, overrides):
    assert_error(post_rep(client, session_id, **overrides), 422, "bad_request")
    assert_nothing_stored(session_id)


def test_an_unsupported_file_type_is_415(client, session_id, started):
    assert_error(post_rep(client, session_id, content_type="text/plain"), 415, "unsupported_type")
    assert_nothing_stored(session_id)


def test_a_file_over_the_size_limit_is_413(client, session_id, started, monkeypatch):
    monkeypatch.setattr("app.takes.routes.MAX_FILE_BYTES", 5)
    assert_error(post_rep(client, session_id, content=b"x" * 10), 413, "file_too_large")
    assert_nothing_stored(session_id)


def test_a_failure_saving_the_take_releases_the_rep_and_removes_the_file(client, session_id, started, monkeypatch):
    def refuse(*args):
        raise storage_error()
    with monkeypatch.context() as failing:
        failing.setattr(store, "update", refuse)
        assert_error(post_rep(client, session_id), 500, "storage_error")
    assert_nothing_stored(session_id)


def test_get_rep_while_processing_shows_only_its_identity_and_status(client, session_id, started):
    post_rep(client, session_id)
    response = client.get(f"/sessions/{session_id}/exercises/ex1/reps/t1")
    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in ("take_id", "exercise_id", "tempo_bpm", "status")} == {
        "take_id": "t1", "exercise_id": "ex1", "tempo_bpm": 60, "status": "processing"}
    assert {k: v for k, v in body.items() if v not in (None, [])} == {
        "take_id": "t1", "exercise_id": "ex1", "tempo_bpm": 60, "status": "processing"}


def test_get_rep_errors(client, session_id, started):
    save_plan(session_id, "pl2", exercise("ex2", 4, 5))
    init_plan(session_id, "pl2")
    post_rep(client, session_id)
    assert_error(client.get(f"/sessions/{session_id}/exercises/ex1/reps/t9"), 404, "rep_not_found")
    assert_error(client.get(f"/sessions/{session_id}/exercises/ex2/reps/t1"), 404, "rep_not_found")
    assert_error(client.get(f"/sessions/{session_id}/exercises/nope/reps/t1"), 404, "exercise_not_found")
    assert_error(client.get(f"/sessions/{'0' * 32}/exercises/ex1/reps/t1"), 404, "session_not_found")


def test_the_started_pipeline_scores_the_rep_and_the_result_replaces_processing(client, session_id, monkeypatch):
    def diagnose(sid, take_id):
        pipeline.update_take(sid, take_id, diagnosis=clean_diagnosis())

    monkeypatch.setattr(pipeline, "extract_audio", lambda *args: None)
    monkeypatch.setattr(pipeline, "resolve_step", lambda module_name, attr="run": diagnose if module_name == "app.diagnosis" else None)
    monkeypatch.setattr("app.takes.pipeline_steps.transcribe", lambda *args: [])
    threads = []
    real_start = rep_routes.start_pipeline
    monkeypatch.setattr(rep_routes, "start_pipeline", lambda sid, take_id: threads.append(real_start(sid, take_id)))
    assert post_rep(client, session_id).status_code == 202
    threads[0].join(timeout=30)
    result = client.get(f"/sessions/{session_id}/exercises/ex1/reps/t1").json()
    assert (result["status"], result["passed"], result["next_bpm"]) == ("scored", True, 60)


def test_a_rep_is_cut_off_at_60_seconds_where_a_take_gets_180(session_id, monkeypatch):
    add_take(session_id, "t1", purpose="rep", exercise_id="ex1", file="t1.wav", audio="t1.wav")
    add_take(session_id, "t2", file="t2.wav", audio="t2.wav")
    monkeypatch.setattr(pipeline, "probe", lambda path: media_tools.MediaInfo(duration_s=90.0, has_audio=True))
    monkeypatch.setattr(pipeline, "extract_wav", lambda *args: None)
    with pytest.raises(media_tools.MediaError) as too_long:
        pipeline.extract_audio(session_id, "t1")
    assert too_long.value.code == "too_long"
    pipeline.extract_audio(session_id, "t2")
    assert store.get(session_id).takes["t2"]["duration_s"] == 90.0


def test_a_too_long_error_names_the_limit_for_the_take_s_purpose(client, session_id):
    add_take(session_id, "t1", purpose="rep", exercise_id="ex1", status="failed", error="too_long")
    add_take(session_id, "t2", status="failed", error="too_long")
    message = lambda take_id: client.get(f"/sessions/{session_id}/takes/{take_id}/analysis").json()["error"]["message"]
    assert message("t1") == "That recording is too long. Keep it under 1 minute."
    assert message("t2") == "That recording is too long. Keep it under 3 minutes."
