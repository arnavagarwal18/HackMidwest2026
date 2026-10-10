import json
import threading
import wave
from pathlib import Path

import pytest

from app import store
from app.takes import media_tools, pipeline
from tests.media_factory import make_silent_video_mp4, make_wav, make_webm_audio
from tests.test_sessions import assert_error

TAKE_FIELDS = {
    "kind": "mic", "source": "recorded", "bar_from": "1", "bar_to": "4",
    "tempo_bpm": "90", "count_in_beats": "4", "downbeat_s": "0.5",
}
TESTDATA = Path(__file__).resolve().parents[2] / "testdata"


def wait_for_pipelines():
    for thread in threading.enumerate():
        if thread.name.startswith("take-"):
            thread.join(timeout=60)


@pytest.fixture(autouse=True)
def settle_pipelines(sessions_root):
    yield
    wait_for_pipelines()


@pytest.fixture
def session_id(client):
    session_id = client.post("/sessions", json={"instrument": "trumpet"}).json()["session_id"]
    store.update(session_id, "score_status", "confirmed")
    return session_id


def post_take(client, session_id, path, content_type, **overrides):
    fields = {k: v for k, v in {**TAKE_FIELDS, **overrides}.items() if v is not None}
    with open(path, "rb") as handle:
        return client.post(f"/sessions/{session_id}/takes", data=fields, files={"file": (path.name, handle, content_type)})


def stored_take(session_id, take_id="t1"):
    return store.get(session_id).takes[take_id]


def test_wav_then_webm_get_t1_then_t2(client, session_id, tmp_path):
    first = post_take(client, session_id, make_wav(tmp_path / "a.wav"), "audio/wav")
    assert first.status_code == 202
    assert first.json() == {"take_id": "t1", "status": "processing"}
    second = post_take(client, session_id, make_webm_audio(tmp_path / "a.webm"), "audio/webm;codecs=opus")
    assert second.json() == {"take_id": "t2", "status": "processing"}
    wait_for_pipelines()
    take = stored_take(session_id)
    assert take["file"] == "t1_upload.wav" and take["audio"] == "t1.wav"
    assert take["purpose"] == "take" and take["status"] == "processing" and take["error"] is None
    assert take["duration_s"] == pytest.approx(1.0, abs=0.1)
    webm_take = stored_take(session_id, "t2")
    assert webm_take["file"] == "t2.webm" and webm_take["error"] is None and webm_take["duration_s"] > 0
    assert client.get(f"/sessions/{session_id}").json()["take_ids"] == ["t1", "t2"]


def test_extracted_wav_is_16khz_mono(client, session_id, tmp_path):
    post_take(client, session_id, make_wav(tmp_path / "quiet.wav", silent=True), "audio/wav")
    wait_for_pipelines()
    with wave.open(str(store.session_dir(session_id) / "t1.wav")) as wav:
        assert (wav.getframerate(), wav.getnchannels()) == (16000, 1)
    assert stored_take(session_id)["error"] is None


def test_uploaded_take_has_no_downbeat(client, session_id, tmp_path):
    response = post_take(client, session_id, make_wav(tmp_path / "a.wav"), "audio/wav", source="uploaded", downbeat_s=None)
    assert response.status_code == 202
    assert stored_take(session_id)["downbeat_s"] is None


def test_text_file_is_unsupported(client, session_id, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")
    response = post_take(client, session_id, notes, "text/plain")
    assert_error(response, 415, "unsupported_type")
    assert "audio/webm" in response.json()["error"]["message"]


def test_take_before_score_confirmed(client, tmp_path):
    session_id = client.post("/sessions", json={"instrument": "violin"}).json()["session_id"]
    assert_error(post_take(client, session_id, make_wav(tmp_path / "a.wav"), "audio/wav"), 409, "wrong_state")


def test_unknown_session(client, tmp_path):
    assert_error(post_take(client, "nope", make_wav(tmp_path / "a.wav"), "audio/wav"), 404, "session_not_found")


@pytest.mark.parametrize("overrides", [
    {"tempo_bpm": "300"}, {"tempo_bpm": "29"}, {"tempo_bpm": "fast"},
    {"downbeat_s": None}, {"downbeat_s": "-1"}, {"bar_from": "5", "bar_to": "4"}, {"bar_from": "0"},
    {"count_in_beats": "9"}, {"kind": "piano"}, {"source": "live"}, {"bar_to": None},
])
def test_bad_fields_are_bad_request(client, session_id, tmp_path, overrides):
    wav = make_wav(tmp_path / "a.wav")
    assert_error(post_take(client, session_id, wav, "audio/wav", **overrides), 422, "bad_request")
    assert store.get(session_id).takes == {}


def test_bar_to_past_last_bar(client, session_id, tmp_path):
    (store.session_dir(session_id) / "score.json").write_text(json.dumps({"bars": [{}] * 8}))
    wav = make_wav(tmp_path / "a.wav")
    assert_error(post_take(client, session_id, wav, "audio/wav", bar_to="9"), 422, "bad_request")
    assert post_take(client, session_id, wav, "audio/wav", bar_to="8").status_code == 202


def test_unreadable_score_skips_bar_check(client, session_id, tmp_path):
    (store.session_dir(session_id) / "score.json").write_text("{not json")
    assert post_take(client, session_id, make_wav(tmp_path / "a.wav"), "audio/wav", bar_to="99").status_code == 202


def test_too_large_file(client, session_id, tmp_path, monkeypatch):
    monkeypatch.setattr("app.takes.routes.MAX_FILE_BYTES", 1000)
    response = post_take(client, session_id, make_wav(tmp_path / "a.wav"), "audio/wav")
    assert_error(response, 413, "file_too_large")
    assert store.get(session_id).takes == {}
    assert list(store.session_dir(session_id).glob("*.tmp")) == []


def test_corrupt_file_is_decode_failed(client, session_id, tmp_path, caplog):
    junk = tmp_path / "junk.wav"
    junk.write_bytes(b"this is definitely not audio" * 50)
    assert post_take(client, session_id, junk, "audio/wav").status_code == 202
    wait_for_pipelines()
    take = stored_take(session_id)
    assert (take["status"], take["error"]) == ("failed", "decode_failed")
    assert "ffmpeg" in caplog.text


def test_video_without_audio(client, session_id, tmp_path):
    video = make_silent_video_mp4(tmp_path / "v.mp4")
    assert post_take(client, session_id, video, "video/mp4", kind="video").status_code == 202
    wait_for_pipelines()
    take = stored_take(session_id)
    assert (take["status"], take["error"]) == ("failed", "no_audio_track")


def test_too_long_file(client, session_id, tmp_path):
    long_wav = make_wav(tmp_path / "long.wav", seconds=181, silent=True)
    post_take(client, session_id, long_wav, "audio/wav")
    wait_for_pipelines()
    take = stored_take(session_id)
    assert (take["status"], take["error"]) == ("failed", "too_long")


def test_missing_ffmpeg_is_decode_failed(client, session_id, tmp_path, monkeypatch, caplog):
    wav = make_wav(tmp_path / "a.wav")
    monkeypatch.setattr(media_tools.imageio_ffmpeg, "get_ffmpeg_exe", lambda: str(tmp_path / "no-ffmpeg"))
    post_take(client, session_id, wav, "audio/wav")
    wait_for_pipelines()
    assert stored_take(session_id)["error"] == "decode_failed"
    assert "ffmpeg" in caplog.text


def test_pipeline_crash_is_recorded(client, session_id, tmp_path, monkeypatch):
    def explode(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "extract_audio", explode)
    post_take(client, session_id, make_wav(tmp_path / "a.wav"), "audio/wav")
    wait_for_pipelines()
    take = stored_take(session_id)
    assert (take["status"], take["error"]) == ("failed", "pipeline_error")


def test_pipeline_runs_one_take_at_a_time_per_session(client, session_id, tmp_path, monkeypatch):
    running, most_at_once, lock = [0], [0], threading.Lock()
    real = pipeline.extract_audio

    def tracked(session_id, take_id):
        with lock:
            running[0] += 1
            most_at_once[0] = max(most_at_once[0], running[0])
        try:
            real(session_id, take_id)
        finally:
            with lock:
                running[0] -= 1

    monkeypatch.setattr(pipeline, "extract_audio", tracked)
    wav = make_wav(tmp_path / "a.wav")
    for _ in range(3):
        post_take(client, session_id, wav, "audio/wav")
    wait_for_pipelines()
    assert most_at_once[0] == 1
    assert all(stored_take(session_id, f"t{n}")["duration_s"] > 0 for n in (1, 2, 3))


def test_media_returns_file_with_range_support(client, session_id, tmp_path):
    wav = make_wav(tmp_path / "a.wav")
    post_take(client, session_id, wav, "audio/wav")
    wait_for_pipelines()
    full = client.get(f"/sessions/{session_id}/takes/t1/media")
    assert full.status_code == 200
    assert "wav" in full.headers["content-type"]
    assert full.content == wav.read_bytes()
    part = client.get(f"/sessions/{session_id}/takes/t1/media", headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and part.content == wav.read_bytes()[:10]


def test_media_errors(client, session_id):
    assert_error(client.get(f"/sessions/{session_id}/takes/t9/media"), 404, "take_not_found")
    assert_error(client.get("/sessions/nope/takes/t1/media"), 404, "session_not_found")


def test_real_trumpet_video_produces_wav(client, session_id):
    post_take(client, session_id, TESTDATA / "trumpet_video1.mp4", "video/mp4", kind="video")
    wait_for_pipelines()
    take = stored_take(session_id)
    assert take["error"] is None, take
    assert take["duration_s"] > 0
    assert (store.session_dir(session_id) / "t1.wav").stat().st_size > 1000
