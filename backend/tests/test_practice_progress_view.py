import pytest

from app import store
from app.practice import init_plan, score_rep
from tests.practice_helpers import add_rep, add_take, diagnosis, exercise, note, save_plan
from tests.test_sessions import assert_error

WHOLE = "pl1:whole"


@pytest.fixture
def session_id(sessions_root):
    return store.create("trumpet").session_id


def diag(errors, played_bpm, bars=(1, 8), cant_tell=False):
    """A diagnosis with `errors` wrong notes then ok notes, spread over the bars."""
    span = range(bars[0], bars[1] + 1)
    notes = [note(bar, "wrong" if i < errors else "ok") for i, bar in enumerate(list(span) * 2)]
    return {**diagnosis(*notes, cant_tell=cant_tell), "played_bpm": played_bpm, "error_rate": errors / len(notes)}


def get_progress(client, session_id):
    response = client.get(f"/sessions/{session_id}/progress")
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def practice(session_id):
    """A first take on bars 1-8 (6 errors at 70 BPM) and a plan with only a 2-bar exercise: 'Put it together' is added."""
    add_take(session_id, "t1", bar_from=1, bar_to=8, tempo_bpm=70.0, diagnosis=diag(6, 70.0))
    save_plan(session_id, "pl1", exercise("ex1", 2, 3, start_bpm=60))
    init_plan(session_id, "pl1")
    return session_id


def rep(session_id, take_id, errors, tempo, exercise_id=WHOLE, bars=(1, 8), **fields):
    add_rep(session_id, take_id, exercise_id, float(tempo), diag(errors, float(tempo), bars), bar_from=bars[0], bar_to=bars[1], **fields)
    score_rep(session_id, take_id)


def test_a_session_without_progress_has_an_empty_view(client, session_id):
    assert get_progress(client, session_id) == {"before": None, "after": None, "exercises": []}


def test_unknown_session_is_404(client):
    assert_error(client.get(f"/sessions/{'0' * 32}/progress"), 404, "session_not_found")


def test_the_best_rep_on_the_before_bars_is_the_after(client, practice):
    rep(practice, "t2", 3, 60)
    rep(practice, "t3", 1, 64)
    view = get_progress(client, practice)
    assert view["before"] == {"source": "take", "take_id": "t1", "bar_from": 1, "bar_to": 8, "errors": 6,
                              "error_rate": 6 / 16, "played_bpm": 70.0, "clean_bpm": 49.0, "form_flags": 0, "form_checked": False}
    assert view["after"]["source"] == "rep"
    assert (view["after"]["take_id"], view["after"]["errors"], view["after"]["played_bpm"]) == ("t3", 1, 64.0)
    assert view["after"]["label"] == "best practice rep at 64 BPM"


def test_equal_errors_go_to_the_higher_tempo_then_the_later_rep(client, practice):
    rep(practice, "t2", 1, 60)
    rep(practice, "t3", 1, 64)
    assert get_progress(client, practice)["after"]["take_id"] == "t3"
    rep(practice, "t4", 1, 64)
    assert get_progress(client, practice)["after"]["take_id"] == "t4"
    rep(practice, "t5", 1, 60)
    assert get_progress(client, practice)["after"]["take_id"] == "t4"


def test_not_counted_failed_and_other_bar_reps_are_never_the_after(client, practice):
    add_rep(practice, "t2", WHOLE, 68.0, diag(0, 68.0, cant_tell=True), bar_from=1, bar_to=8)
    score_rep(practice, "t2")
    add_rep(practice, "t3", WHOLE, 68.0, diag(0, 68.0), bar_from=1, bar_to=8, status="failed", error="no_notes_heard")
    score_rep(practice, "t3")
    rep(practice, "t4", 0, 70, exercise_id="ex1", bars=(2, 3))
    view = get_progress(client, practice)
    assert [r["status"] for r in (store.get(practice).progress["reps"][t] for t in ("t2", "t3", "t4"))] == ["not_counted", "failed", "scored"]
    assert view["after"] is None


def test_the_after_is_null_before_any_matching_rep(client, practice):
    assert get_progress(client, practice)["after"] is None


def test_a_later_full_take_does_not_replace_the_after(client, practice):
    rep(practice, "t2", 2, 60)
    add_take(practice, "t3", bar_from=1, bar_to=8, diagnosis=diag(0, 90.0))
    view = get_progress(client, practice)
    assert (view["before"]["take_id"], view["after"]["take_id"]) == ("t1", "t2")


def test_a_cant_tell_take_is_never_the_before(client, session_id):
    add_take(session_id, "t1", bar_from=1, bar_to=8, diagnosis=diag(0, 70.0, cant_tell=True))
    add_take(session_id, "t2", bar_from=1, bar_to=8, tempo_bpm=70.0, diagnosis=diag(4, 70.0))
    save_plan(session_id, "pl1", exercise("ex1", 2, 3))
    init_plan(session_id, "pl1")
    view = get_progress(client, session_id)
    assert (view["before"]["take_id"], view["before"]["errors"]) == ("t2", 4)


def test_snapshot_clean_tempo_and_form_flags(client, practice):
    store.update(practice, "takes", {**store.get(practice).takes, "t1": {
        **store.get(practice).takes["t1"], "kind": "video", "form_status": "done", "form": {"flags": [{"id": "f1"}, {"id": "f2"}]},
        "diagnosis": diag(0, 56.0)}})
    before = get_progress(client, practice)["before"]
    assert (before["clean_bpm"], before["form_flags"], before["form_checked"]) == (56.0, 2, True)


def test_the_before_clean_tempo_stays_fixed_when_later_reps_change_the_shared_clean_tempo(client, session_id):
    add_take(session_id, "t1", bar_from=1, bar_to=16, tempo_bpm=70.0, diagnosis=diag(1, 44.69, bars=(1, 16)))
    save_plan(session_id, "pl1", exercise("ex1", 2, 3, start_bpm=60))
    init_plan(session_id, "pl1")
    store.update(session_id, "clean_tempo", {"1-16": 44.69})  # what the pipeline saved for the before take
    rep(session_id, "t2", 0, 62.02, bars=(1, 16))
    store.update(session_id, "clean_tempo", {"1-16": 62.02})  # what the pipeline saved after the rep
    view = get_progress(client, session_id)
    assert view["before"]["clean_bpm"] == 44.69
    assert view["after"]["take_id"] == "t2" and view["after"]["clean_bpm"] == 62.02
    rep(session_id, "t3", 0, 66, bars=(1, 16))
    store.update(session_id, "clean_tempo", {"1-16": 66.0})
    assert get_progress(client, session_id)["before"]["clean_bpm"] == 44.69


def test_the_before_clean_tempo_counts_only_takes_recorded_before_it(client, session_id):
    add_take(session_id, "t0", bar_from=1, bar_to=8, tempo_bpm=70.0, purpose="warmup", diagnosis=diag(0, 80.0))
    add_take(session_id, "t1", bar_from=1, bar_to=8, tempo_bpm=70.0, diagnosis=diag(0, 50.0))
    add_take(session_id, "t2", bar_from=1, bar_to=8, tempo_bpm=70.0, diagnosis=diag(0, 90.0))
    save_plan(session_id, "pl1", exercise("ex1", 2, 3))
    init_plan(session_id, "pl1")
    assert get_progress(client, session_id)["before"]["clean_bpm"] == 80.0


def test_extras_count_as_errors(client, practice):
    takes = store.get(practice).takes
    store.update(practice, "takes", {**takes, "t1": {**takes["t1"], "diagnosis": {**diag(1, 70.0), "extras": [{"bar": 2}, {"bar": 3}]}}})
    assert get_progress(client, practice)["before"]["errors"] == 3


def test_exercises_count_scored_reps_and_passes(client, practice):
    rep(practice, "t2", 3, 60)  # fails the pass mark of 1 error
    rep(practice, "t3", 1, 64)  # passes
    add_rep(practice, "t4", "ex1", 60.0, diagnosis(note(2), note(3)))
    score_rep(practice, "t4")
    add_rep(practice, "t5", "ex1", 60.0, diag(0, 60.0, (2, 3), cant_tell=True))
    score_rep(practice, "t5")  # not counted
    exercises = {ex["id"]: ex for ex in get_progress(client, practice)["exercises"]}
    assert list(exercises) == ["ex1", WHOLE]
    assert exercises[WHOLE] == {"id": WHOLE, "title": "Put it together", "start_bpm": 60, "target_bpm": 70.0,
                                "best_passed_bpm": 64.0, "complete": False, "reps": 2, "passes": 1}
    assert (exercises["ex1"]["reps"], exercises["ex1"]["passes"]) == (1, 1)


def test_get_exercise_returns_the_plan_exercise_and_the_added_put_it_together(client, practice):
    planned = client.get(f"/sessions/{practice}/exercises/ex1").json()
    assert planned["exercise"]["id"] == "ex1" and planned["state"]["current_bpm"] == 60
    added = client.get(f"/sessions/{practice}/exercises/{WHOLE}").json()
    assert added["exercise"]["title"] == "Put it together"
    assert (added["exercise"]["bar_from"], added["exercise"]["bar_to"]) == (1, 8)
    assert (added["state"]["added_by"], added["state"]["complete"]) == ("practice", False)


def test_get_exercise_errors(client, practice):
    assert_error(client.get(f"/sessions/{practice}/exercises/nope"), 404, "exercise_not_found")
    assert_error(client.get(f"/sessions/{'0' * 32}/exercises/ex1"), 404, "session_not_found")
