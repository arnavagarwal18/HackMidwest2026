import json
import logging

import pytest

from app import diagnosis, store
from app.diagnosis import runner
from app.errors import STORAGE_ERROR_MESSAGE, storage_error
from app.takes import pipeline
from app.takes.take_store import add_take, get_take, update_take
from app.takes.transcribe import PlayedNote
from app.takes.validation import TakeRequest, new_take_fields
from diagnosis_samples import SCALE_BARS, make_scale_score, make_score, perfect_played, played_note
from diagnosis_session import add_transcribed_take, diagnosed_session, make_session
from tests.media_factory import make_wav
from tests.test_sessions import assert_error

SCALE_MIDIS = [midi for bar in SCALE_BARS for midi in bar]
ANALYSIS_KEYS = {
    "status", "error", "form_status", "calibrated", "transposition", "alignment_quality", "cant_tell",
    "cant_tell_reason", "tempo", "notes", "extras", "outside_count", "bars", "problems", "tier1", "form", "media_url",
}


def analysis(client, session_id, take_id="t1"):
    return client.get(f"/sessions/{session_id}/takes/{take_id}/analysis")


def late_bar_three() -> list[dict]:
    played = perfect_played(SCALE_MIDIS)
    for index in range(8, 12):
        played[index]["onset_s"] += 0.1
    return played


def test_unknown_session_and_take_are_404(client, sessions_root):
    assert_error(analysis(client, "nosuchsession"), 404, "session_not_found")
    session_id = make_session(make_scale_score())
    assert_error(analysis(client, session_id, "t9"), 404, "take_not_found")


def test_analysis_before_diagnosis_has_empty_results(client, sessions_root):
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, perfect_played(SCALE_MIDIS))

    body = analysis(client, session_id, take_id).json()

    assert set(body) == ANALYSIS_KEYS
    assert (body["status"], body["error"], body["transposition"], body["tempo"]) == ("transcribed", None, None, None)
    assert (body["notes"], body["extras"], body["bars"], body["problems"], body["tier1"], body["form"]) == ([],) * 6
    assert body["media_url"] == f"/sessions/{session_id}/takes/t1/media"


def test_analysis_after_diagnosis_follows_the_contract(client, sessions_root):
    session_id, take_id = diagnosed_session(late_bar_three())

    body = analysis(client, session_id, take_id).json()

    assert set(body) == ANALYSIS_KEYS
    assert (body["status"], body["error"], body["cant_tell"], body["cant_tell_reason"]) == ("diagnosed", None, False, None)
    assert body["transposition"] == {"semitones": 0, "source": "default"}
    assert body["alignment_quality"] == 1.0
    assert body["tempo"]["target_bpm"] == 120
    assert body["tempo"]["played_bpm"] == pytest.approx(120, abs=1)
    assert body["tempo"]["clean_bpm"] == pytest.approx(0.7 * body["tempo"]["played_bpm"], abs=0.01)  # no clean take yet
    assert len(body["notes"]) == 16 and len(body["bars"]) == 4
    assert body["problems"][0]["kind"] == "late"
    assert body["tier1"][0]["text"] == "Bar 3: 4 notes late, 100 ms on average."


def test_first_diagnosed_take_locks_the_transposition(sessions_root):
    session_id, _ = diagnosed_session(perfect_played(SCALE_MIDIS))

    assert store.get(session_id).transposition == {"semitones": 0, "source": "default"}


def test_diagnosis_is_saved_in_the_session_file_and_its_own_file(sessions_root):
    session_id, take_id = diagnosed_session(late_bar_three())

    saved = json.loads((store.session_dir(session_id) / "t1_diagnosis.json").read_text())
    in_session = json.loads((store.session_dir(session_id) / "session.json").read_text())["takes"]["t1"]
    assert saved == in_session["diagnosis"] == diagnosis.get(session_id, take_id)
    assert (in_session["status"], in_session["error"]) == ("diagnosed", None)
    assert list(saved)[:2] == ["transposition", "latency_ms"] and "tier1" in saved


def test_take_without_confirmed_score_fails_with_no_score(client, sessions_root):
    session_id = make_session(make_scale_score(), confirmed=False)
    take_id = add_transcribed_take(session_id, perfect_played(SCALE_MIDIS))

    diagnosis.run(session_id, take_id)

    body = analysis(client, session_id, take_id).json()
    assert body["status"] == "failed"
    assert body["error"] == {"code": "no_score", "message": "Confirm a score before recording."}


def test_confirmed_session_with_a_missing_score_file_fails_with_no_score(sessions_root):
    session_id = make_session(score=None)
    take_id = add_transcribed_take(session_id, perfect_played(SCALE_MIDIS))

    diagnosis.run(session_id, take_id)

    take = get_take(session_id, take_id)
    assert (take["status"], take["error"]) == ("failed", "no_score")


def test_exception_in_alignment_fails_with_diagnosis_failed(client, sessions_root, monkeypatch, caplog):
    def explode(*args, **kwargs):
        raise RuntimeError("alignment blew up")

    monkeypatch.setattr(runner, "align_with_transposition", explode)
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, perfect_played(SCALE_MIDIS))

    with caplog.at_level(logging.ERROR):
        diagnosis.run(session_id, take_id)

    body = analysis(client, session_id, take_id).json()
    assert body["status"] == "failed"
    assert body["error"] == {"code": "diagnosis_failed", "message": "Note check failed on this take."}
    assert f"{session_id}/{take_id}" in caplog.text and "RuntimeError: alignment blew up" in caplog.text
    assert "diagnosis" not in get_take(session_id, take_id)


def test_failed_save_records_storage_error(client, sessions_root, monkeypatch):
    def refuse(*args, **kwargs):
        raise storage_error()

    monkeypatch.setattr(runner, "save_diagnosis", refuse)
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, perfect_played(SCALE_MIDIS))

    diagnosis.run(session_id, take_id)

    error = analysis(client, session_id, take_id).json()["error"]
    assert error == {"code": "storage_error", "message": STORAGE_ERROR_MESSAGE}


def test_no_played_notes_is_cant_tell_with_no_problems(sessions_root):
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, [])

    diagnosis.run(session_id, take_id)

    saved = get_take(session_id, take_id)
    assert saved["status"] == "diagnosed"
    assert saved["diagnosis"]["cant_tell"] is True
    assert (saved["diagnosis"]["problems"], saved["diagnosis"]["tier1"]) == ([], [])
    assert store.get(session_id).transposition is None  # a take we can't read doesn't lock the transposition


def test_few_expected_notes_is_too_short(client, sessions_root):
    session_id = make_session(make_score([[60, 62]]))
    take_id = add_transcribed_take(session_id, perfect_played([60, 62]), bar_to=1)

    diagnosis.run(session_id, take_id)

    body = analysis(client, session_id, take_id).json()
    assert (body["status"], body["cant_tell"], body["cant_tell_reason"], body["problems"]) == (
        "diagnosed", True, "too_short", [],
    )


def test_played_nothing_like_the_score_is_low_match(sessions_root):
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, [played_note(i, 1.0 + i * 0.5, 90) for i in range(16)])

    diagnosis.run(session_id, take_id)

    assert get_take(session_id, take_id)["diagnosis"]["cant_tell_reason"] == "low_match"


def test_a_take_that_never_reached_transcription_is_skipped(sessions_root):
    session_id = make_session(make_scale_score())
    take_id = add_transcribed_take(session_id, [], status="processing")

    diagnosis.run(session_id, take_id)

    assert "diagnosis" not in get_take(session_id, take_id)
    assert get_take(session_id, take_id)["status"] == "processing"


def test_a_rerun_keeps_a_done_take_done(sessions_root):
    session_id, take_id = diagnosed_session(perfect_played(SCALE_MIDIS))
    update_take(session_id, take_id, status="done")

    diagnosis.run(session_id, take_id)

    assert get_take(session_id, take_id)["status"] == "done"


def test_lookup_finds_each_kind_of_item(sessions_root):
    played = perfect_played(SCALE_MIDIS)
    played[0] = played_note(0, 1.0, 61, 0.9)  # wrong note in bar 1
    played.append(played_note(16, 1.25, 70, 0.9))  # extra note
    session_id, take_id = diagnosed_session(played)
    saved = diagnosis.get(session_id, take_id)
    update_take(session_id, take_id, form={"status": "ok", "flags": [{"id": "f:t1:0", "bars": [2]}]})

    assert diagnosis.lookup(session_id, "n:t1:1:0") == saved["notes"][0]
    assert diagnosis.lookup(session_id, "x:t1:16") == saved["extras"][0]
    assert diagnosis.lookup(session_id, "b:t1:2") == saved["bars"][1]
    assert diagnosis.lookup(session_id, "p:t1:0") == saved["problems"][0]
    assert diagnosis.lookup(session_id, "f:t1:0") == {"id": "f:t1:0", "bars": [2]}


@pytest.mark.parametrize("measurement_id", ["n:t1:9:9", "p:t1:99", "n:t7:1:0", "nonsense", "", "n:t1"])
def test_lookup_of_an_unknown_id_is_none(sessions_root, measurement_id):
    session_id, _ = diagnosed_session(perfect_played(SCALE_MIDIS))

    assert diagnosis.lookup(session_id, measurement_id) is None


def test_lookup_in_an_unknown_session_is_none(sessions_root):
    assert diagnosis.lookup("nosuchsession", "n:t1:1:0") is None


def pipeline_take(session_id, tmp_path):
    request = TakeRequest(
        kind="mic", source="recorded", bar_from=1, bar_to=4, tempo_bpm=120, count_in_beats=4, downbeat_s=1.0
    )
    wav = make_wav(tmp_path / "a.wav")
    take = add_take(
        session_id,
        lambda take_id: new_take_fields(take_id, request, f"{take_id}_upload.wav"),
        lambda take: (store.session_dir(session_id) / take["file"]).write_bytes(wav.read_bytes()),
    )
    return take["take_id"]


def transcriber_of(played):
    notes = [PlayedNote(**{key: note[key] for key in PlayedNote.__dataclass_fields__}) for note in played]
    return lambda wav_path, instrument, profile, calib_end_s: notes


def test_pipeline_with_the_real_diagnosis_ends_done(client, sessions_root, tmp_path):
    session_id = make_session(make_scale_score())
    take_id = pipeline_take(session_id, tmp_path)

    pipeline.run_take_pipeline(session_id, take_id, transcriber=transcriber_of(late_bar_three()))

    body = analysis(client, session_id, take_id).json()
    assert (body["status"], body["error"]) == ("done", None)
    assert body["tier1"][0]["text"] == "Bar 3: 4 notes late, 100 ms on average."


def test_pipeline_keeps_the_no_score_failure(client, sessions_root, tmp_path):
    session_id = make_session(make_scale_score(), confirmed=False)
    take_id = pipeline_take(session_id, tmp_path)

    pipeline.run_take_pipeline(session_id, take_id, transcriber=transcriber_of(perfect_played(SCALE_MIDIS)))

    body = analysis(client, session_id, take_id).json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "no_score"


def test_analysis_reports_outside_notes_and_defaults_to_zero_for_old_diagnoses(client, sessions_root):
    trailing = [played_note(16 + n, 1.0 + (20 + n) * 0.5, 70 + n) for n in range(10)]
    session_id, take_id = diagnosed_session(perfect_played(SCALE_MIDIS) + trailing)

    body = analysis(client, session_id, take_id).json()

    assert (body["outside_count"], body["extras"], body["problems"]) == (10, [], [])
    old = {key: value for key, value in diagnosis.get(session_id, take_id).items() if key != "outside_count"}
    update_take(session_id, take_id, diagnosis=old)
    assert analysis(client, session_id, take_id).json()["outside_count"] == 0
