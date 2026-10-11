import logging
import random

import pytest

import app.diagnosis
from app import store
from app.diagnosis import config, transposition
from app.diagnosis.take_alignment import align_take
from tests.diagnosis_samples import SCALE_BARS, make_scale_score, make_score, make_take, perfect_played, played_note
from app.takes.take_store import get_take
from tests.diagnosis_session import add_transcribed_take, make_session
from tests.test_sessions import assert_error

SCALE_MIDIS = [midi for bar in SCALE_BARS for midi in bar]
DEFAULT_BASE = {"semitones": -2, "source": "default"}


def scale_with(written_transpose=None) -> dict:
    return {**make_scale_score(), "written_transpose_semitones": written_transpose}


def fake_qualities(monkeypatch, quality_by_semitones: dict) -> None:
    monkeypatch.setattr(
        transposition, "align_take",
        lambda score, played, take, semitones: {"alignment_quality": quality_by_semitones.get(semitones, 0.0)},
    )


# ---- Test 6: can't tell -------------------------------------------------------------------

def test_random_notes_cant_tell_and_still_save_notes():
    rng = random.Random(11)
    played = [played_note(i, 1.0 + i * 0.5, rng.randint(40, 90)) for i in range(16)]
    result = align_take(make_scale_score(), played, make_take(), 0)
    assert result["cant_tell"] is True
    assert result["cant_tell_reason"] in (config.CANT_TELL_LOW_MATCH, config.CANT_TELL_FEW_PAIRS)
    assert len(result["notes"]) == 16
    assert "problems" not in result


def test_no_played_notes_cant_tell_low_match():
    result = align_take(make_scale_score(), [], make_take(), 0)
    assert (result["cant_tell"], result["cant_tell_reason"]) == (True, config.CANT_TELL_LOW_MATCH)


def test_two_note_range_is_too_short():
    result = align_take(make_score([[60, 62]]), perfect_played([60, 62]), make_take(bar_to=1), 0)
    assert (result["cant_tell"], result["cant_tell_reason"]) == (True, config.CANT_TELL_TOO_SHORT)


# ---- Test 7: transposition detection ------------------------------------------------------

def test_base_uses_file_transposition_then_instrument_default():
    assert transposition.base_transposition(scale_with(-3), "trumpet") == {"semitones": -3, "source": "file"}
    assert transposition.base_transposition(scale_with(0), "trumpet") == {"semitones": 0, "source": "file"}
    assert transposition.base_transposition(scale_with(), "trumpet") == DEFAULT_BASE
    assert transposition.base_transposition(scale_with(), "violin") == {"semitones": 0, "source": "default"}


def test_concert_pitch_trumpet_take_switches_to_zero_as_detected():
    chosen, alignment = transposition.align_with_transposition(
        scale_with(), perfect_played(SCALE_MIDIS), make_take(), "trumpet", None
    )
    assert chosen == {"semitones": 0, "source": "detected"}
    assert alignment["alignment_quality"] == 1.0


def test_base_is_kept_when_it_lines_up_best():
    played = perfect_played([m - 2 for m in SCALE_MIDIS])
    chosen, alignment = transposition.align_with_transposition(scale_with(), played, make_take(), "trumpet", None)
    assert chosen == DEFAULT_BASE
    assert alignment["alignment_quality"] == 1.0


def test_base_is_kept_when_the_gain_is_under_point_one_five(monkeypatch):
    fake_qualities(monkeypatch, {-2: 0.5, 0: 0.6})
    chosen, _ = transposition.detect_transposition(scale_with(), [], make_take(), DEFAULT_BASE)
    assert chosen == DEFAULT_BASE


def test_gain_of_exactly_point_one_five_switches(monkeypatch):
    fake_qualities(monkeypatch, {-2: 0.5, 0: 0.65})
    chosen, _ = transposition.detect_transposition(scale_with(), [], make_take(), DEFAULT_BASE)
    assert chosen == {"semitones": 0, "source": "detected"}


def test_best_candidate_wins_when_several_beat_the_base(monkeypatch):
    fake_qualities(monkeypatch, {-2: 0.2, 0: 0.6, -7: 0.9})
    chosen, _ = transposition.detect_transposition(scale_with(), [], make_take(), DEFAULT_BASE)
    assert chosen == {"semitones": -7, "source": "detected"}


def test_locked_transposition_is_reused_without_trying_candidates(monkeypatch):
    calls = []

    def counting_align(score, played, take, semitones):
        calls.append(semitones)
        return align_take(score, played, take, semitones)

    monkeypatch.setattr(transposition, "align_take", counting_align)
    locked = {"semitones": 0, "source": "detected"}
    chosen, _ = transposition.align_with_transposition(
        scale_with(), perfect_played(SCALE_MIDIS), make_take(), "trumpet", locked
    )
    assert chosen == locked
    assert calls == [0]


def test_candidates_cover_the_range_nearest_the_base_first():
    candidates = transposition._candidates(-2)
    assert len(candidates) == 25 and sorted(candidates) == list(range(-12, 13))
    assert candidates[:5] == [-2, -3, -1, -4, 0]


def test_candidates_include_a_base_outside_the_range():
    assert transposition._candidates(14)[0] == 14


def test_ties_go_to_the_offset_nearest_the_base(monkeypatch):
    fake_qualities(monkeypatch, {-2: 0.2, -4: 0.8, 0: 0.8, 5: 0.8})
    chosen, _ = transposition.detect_transposition(scale_with(), [], make_take(), DEFAULT_BASE)
    assert chosen == {"semitones": -4, "source": "detected"}


def test_a_base_that_cannot_be_beaten_skips_the_search(monkeypatch):
    calls = []

    def counting_align(score, played, take, semitones):
        calls.append(semitones)
        return {"alignment_quality": 0.9}

    monkeypatch.setattr(transposition, "align_take", counting_align)
    chosen, _ = transposition.detect_transposition(scale_with(), [], make_take(), DEFAULT_BASE)
    assert chosen == DEFAULT_BASE and calls == [-2]


def test_search_reaches_offsets_beyond_the_old_fixed_list():
    played = perfect_played([m + 5 for m in SCALE_MIDIS])
    chosen, alignment = transposition.align_with_transposition(scale_with(), played, make_take(), "trumpet", None)
    assert chosen == {"semitones": 5, "source": "detected"}
    assert alignment["alignment_quality"] == 1.0


# ---- Test 7: detection through diagnosis.run ----------------------------------------------

# A scale lines up partly at neighbouring offsets, so these tests use a leapy tune that doesn't.
TUNE_BARS = [[60, 67, 62, 71], [64, 59, 69, 65], [72, 61, 66, 70], [63, 68, 58, 73]]
TUNE_MIDIS = [midi for bar in TUNE_BARS for midi in bar]


def trumpet_session() -> str:
    return make_session(make_score(TUNE_BARS), instrument="trumpet")


def diagnose(session_id: str, midis: list[int]) -> dict:
    take_id = add_transcribed_take(session_id, perfect_played(midis))
    app.diagnosis.run(session_id, take_id)
    return get_take(session_id, take_id)["diagnosis"]


def test_take_four_semitones_below_the_written_part_is_detected(sessions_root):
    session_id = trumpet_session()

    result = diagnose(session_id, [m - 4 for m in TUNE_MIDIS])

    assert result["transposition"] == {"semitones": -4, "source": "detected"}
    assert result["cant_tell"] is False
    assert store.get(session_id).transposition == {"semitones": -4, "source": "detected"}


def test_user_transposition_is_never_searched(sessions_root, monkeypatch):
    session_id = trumpet_session()
    user = {"semitones": -2, "source": "user"}
    store.update(session_id, "transposition", user)
    searched = []
    monkeypatch.setattr(transposition, "detect_transposition", lambda *args: searched.append(args))

    result = diagnose(session_id, [m - 4 for m in TUNE_MIDIS])

    assert searched == []
    assert result["transposition"] == user
    assert (result["cant_tell"], result["cant_tell_reason"]) == (True, "low_match")
    assert store.get(session_id).transposition == user


def test_later_low_match_take_searches_again(sessions_root):
    session_id = trumpet_session()
    assert diagnose(session_id, [m - 2 for m in TUNE_MIDIS])["transposition"] == DEFAULT_BASE

    result = diagnose(session_id, [m - 4 for m in TUNE_MIDIS])

    assert result["transposition"] == {"semitones": -4, "source": "detected"}
    assert result["cant_tell"] is False
    assert store.get(session_id).transposition == {"semitones": -4, "source": "detected"}


def test_later_good_take_does_not_search(sessions_root, monkeypatch):
    session_id = trumpet_session()
    diagnose(session_id, [m - 4 for m in TUNE_MIDIS])
    monkeypatch.setattr(transposition, "detect_transposition", lambda *args: pytest.fail("searched"))

    result = diagnose(session_id, [m - 4 for m in TUNE_MIDIS])

    assert result["transposition"] == {"semitones": -4, "source": "detected"}


def test_earlier_takes_keep_their_diagnosis_until_rerun(sessions_root):
    session_id = trumpet_session()
    first = add_transcribed_take(session_id, perfect_played([m - 2 for m in TUNE_MIDIS]))
    app.diagnosis.run(session_id, first)
    saved = get_take(session_id, first)["diagnosis"]
    diagnose(session_id, [m - 4 for m in TUNE_MIDIS])

    assert get_take(session_id, first)["diagnosis"] == saved


def test_unmatchable_take_stays_cant_tell_and_keeps_the_session_unlocked(sessions_root):
    session_id = trumpet_session()

    result = diagnose(session_id, [30, 31, 30, 31, 30, 31, 30, 31, 30, 31, 30, 31, 30, 31, 30, 31])

    assert result["cant_tell"] is True
    assert store.get(session_id).transposition is None


# ---- Test 7: POST /transposition ----------------------------------------------------------

@pytest.fixture
def confirmed_session(client):
    session_id = client.post("/sessions", json={"instrument": "trumpet"}).json()["session_id"]
    store.update(session_id, "score_status", "confirmed")
    store.update(session_id, "takes", {"t1": {"take_id": "t1"}, "t2": {"take_id": "t2"}})
    return session_id


@pytest.fixture
def run_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(app.diagnosis, "run", lambda session_id, take_id: calls.append((session_id, take_id)), raising=False)
    return calls


def post_transposition(client, session_id, body):
    return client.post(f"/sessions/{session_id}/transposition", json=body)


def test_post_transposition_sets_user_source_and_reruns_every_take(client, confirmed_session, run_calls):
    response = post_transposition(client, confirmed_session, {"semitones": -2})
    assert response.status_code == 200
    assert response.json() == {"transposition": {"semitones": -2, "source": "user"}, "rerun_takes": ["t1", "t2"]}
    assert store.get(confirmed_session).transposition == {"semitones": -2, "source": "user"}
    assert run_calls == [(confirmed_session, "t1"), (confirmed_session, "t2")]


def test_post_transposition_persists_to_disk(client, confirmed_session, run_calls):
    post_transposition(client, confirmed_session, {"semitones": 3})
    store._sessions.clear()
    assert store.get(confirmed_session).transposition == {"semitones": 3, "source": "user"}


@pytest.mark.parametrize(
    "body",
    [{"semitones": 20}, {"semitones": -13}, {"semitones": 1.5}, {"semitones": "2"}, {"semitones": True},
     {"semitones": None}, {}],
)
def test_bad_transposition_is_422_and_changes_nothing(client, confirmed_session, run_calls, body):
    locked = {"semitones": 0, "source": "detected"}
    store.update(confirmed_session, "transposition", locked)
    assert_error(post_transposition(client, confirmed_session, body), 422, "bad_request")
    assert store.get(confirmed_session).transposition == locked
    assert run_calls == []


@pytest.mark.parametrize("semitones", [-12, 12])
def test_range_limits_are_accepted(client, confirmed_session, run_calls, semitones):
    assert post_transposition(client, confirmed_session, {"semitones": semitones}).status_code == 200


def test_unknown_session_is_404(client):
    assert_error(post_transposition(client, "nope", {"semitones": 0}), 404, "session_not_found")


def test_unconfirmed_score_is_409_and_changes_nothing(client, run_calls):
    session_id = client.post("/sessions", json={"instrument": "trumpet"}).json()["session_id"]
    assert_error(post_transposition(client, session_id, {"semitones": 0}), 409, "wrong_state")
    assert store.get(session_id).transposition is None
    assert run_calls == []


def test_rerun_skips_with_a_warning_when_diagnosis_run_is_missing(client, confirmed_session, caplog, monkeypatch):
    monkeypatch.delattr(app.diagnosis, "run", raising=False)
    with caplog.at_level(logging.WARNING, logger="app.diagnosis"):
        response = post_transposition(client, confirmed_session, {"semitones": 0})
    assert response.status_code == 200
    assert "app.diagnosis.run doesn't exist yet" in caplog.text


def test_one_failing_rerun_does_not_stop_the_others(client, confirmed_session, monkeypatch, caplog):
    seen = []

    def flaky(session_id, take_id):
        seen.append(take_id)
        if take_id == "t1":
            raise RuntimeError("boom")

    monkeypatch.setattr(app.diagnosis, "run", flaky, raising=False)
    with caplog.at_level(logging.ERROR, logger="app.diagnosis"):
        assert post_transposition(client, confirmed_session, {"semitones": 0}).status_code == 200
    assert seen == ["t1", "t2"]
    assert "Diagnosis rerun failed for take" in caplog.text
