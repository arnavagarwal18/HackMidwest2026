"""A take through the real runner with the real form.run on a synthetic video (the fixture photo, with a tone for audio)."""
import json

import pytest

from app import form, store
from app.takes import pipeline
from app.takes.take_store import add_take
from app.takes.transcribe import PlayedNote
from app.takes.validation import TakeRequest, new_take_fields
from tests.form_helpers import make_photo_video_with_audio

NOTE = PlayedNote(i=0, onset_s=0.1, offset_s=0.6, midi_float=69.1, midi=69, cents_off=10.0, confidence=0.9, voiced_ratio=0.95)
BARS = [{"bar": n, "start_beat": 4.0 * (n - 1), "beats": 4.0, "notes": []} for n in range(1, 5)]


@pytest.fixture
def session_id(sessions_root, monkeypatch):
    monkeypatch.setattr("app.diagnosis.rerank", lambda session_id, take_id: None)
    session_id = store.create("trumpet").session_id
    store.session_dir(session_id).mkdir(parents=True, exist_ok=True)
    (store.session_dir(session_id) / "score.json").write_text(json.dumps({"bars": BARS}), encoding="utf-8")
    return session_id


def add_video_take(session_id, tmp_path, kind="video"):
    request = TakeRequest(kind=kind, source="recorded", bar_from=1, bar_to=4, tempo_bpm=90, count_in_beats=4, downbeat_s=0.5)
    video = make_photo_video_with_audio(tmp_path / "take.mp4", tmp_path)
    take = add_take(session_id, lambda take_id: new_take_fields(take_id, request, f"{take_id}_upload.mp4"),
                    lambda take: (store.session_dir(session_id) / take["file"]).write_bytes(video.read_bytes()))
    return take["take_id"]


def run_pipeline(session_id, take_id, order):
    pipeline.run_take_pipeline(session_id, take_id, transcriber=lambda *args: [NOTE],
                               diagnose=lambda s, t: order.append("diagnose"), give_feedback=lambda s, t: order.append("feedback"))
    return store.get(session_id).takes[take_id]


def test_video_take_gets_its_form_check_after_diagnosis(session_id, tmp_path, monkeypatch):
    order = []
    real_run = form.run
    monkeypatch.setattr(form, "run", lambda s, t: (order.append("form"), real_run(s, t)))
    take = run_pipeline(session_id, add_video_take(session_id, tmp_path), order)
    assert order == ["diagnose", "form", "feedback"]
    assert (take["status"], take["error"], take["form_status"]) == ("done", None, "done")
    assert take["form"]["error"] is None
    assert take["form"]["frames_tracked"] > 0


def test_mic_take_is_never_sent_to_form(session_id, tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(form, "run", lambda s, t: sent.append(t))
    take = run_pipeline(session_id, add_video_take(session_id, tmp_path, kind="mic"), [])
    assert sent == []
    assert (take["status"], take["form_status"]) == ("done", "none")


def test_form_failing_leaves_the_notes_and_the_take_intact(session_id, tmp_path, monkeypatch):
    def broken(session_id, take_id):
        raise RuntimeError("tracker exploded")

    monkeypatch.setattr(form, "run", broken)
    order = []
    take = run_pipeline(session_id, add_video_take(session_id, tmp_path), order)
    assert order == ["diagnose", "feedback"]
    assert (take["status"], take["error"], take["form_status"]) == ("done", None, "failed")
    assert take["notes"] == [NOTE.to_dict()]

