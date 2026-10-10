import subprocess

import numpy as np
import pytest
import soundfile as sf

from app import store
from app.takes.media_tools import ffmpeg_exe
from app.takes.reference import REFERENCE_NOTES
from tests.test_sessions import assert_error

SAMPLE_RATE = 16000
BACKGROUND_DB = -70.0
CLICK_AT_S = 0.5


def background(length: int, rng, db: float = BACKGROUND_DB) -> np.ndarray:
    return rng.normal(0, 10 ** (db / 20), size=length)


def make_note_clip(path, hz, cents=0.0, amplitude=0.3, noise_db=BACKGROUND_DB, seconds=2.0, silent=False):
    """A sine note with a quiet lead-in and tail (so there are quiet frames to measure noise from)."""
    rng = np.random.default_rng(1)
    pad = int(0.4 * SAMPLE_RATE)
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    tone = np.zeros_like(t) if silent else amplitude * np.sin(2 * np.pi * hz * 2 ** (cents / 1200) * t)
    audio = np.concatenate([np.zeros(pad), tone, np.zeros(pad)])
    audio = audio + background(len(audio), rng, noise_db)
    sf.write(path, audio.astype(np.float32), SAMPLE_RATE)
    return path


def make_click_clip(path, click_at_s, latency_s, seconds=1.5):
    rng = np.random.default_rng(2)
    audio = background(int(seconds * SAMPLE_RATE), rng)
    start = int((click_at_s + latency_s) * SAMPLE_RATE)
    burst = np.arange(int(0.005 * SAMPLE_RATE))
    audio[start: start + len(burst)] += 0.5 * np.sin(2 * np.pi * 2000 * burst / SAMPLE_RATE)
    sf.write(path, audio.astype(np.float32), SAMPLE_RATE)
    return path


def to_webm(wav_path):
    target = wav_path.with_suffix(".webm")
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path),
                    "-c:a", "libopus", str(target)], check=True)
    return target


@pytest.fixture
def violin_session(client):
    return client.post("/sessions", json={"instrument": "violin"}).json()["session_id"]


def post_calibration(client, session_id, tmp_path, cents=(0.0, 0.0, 0.0), latency_s=0.12, instrument="violin",
                     clips=None, **extra_files):
    clips = clips or [make_note_clip(tmp_path / f"ref_{i}.wav", note.hz, cents[i])
                      for i, note in enumerate(REFERENCE_NOTES[instrument])]
    files = {f"ref_{i}": (clip.name, clip.open("rb"), "audio/wav") for i, clip in enumerate(clips)}
    click = make_click_clip(tmp_path / "click.wav", CLICK_AT_S, latency_s)
    files["click"] = (click.name, click.open("rb"), "audio/wav")
    files.update({name: (path.name, path.open("rb"), "audio/wav") for name, path in extra_files.items()})
    try:
        return client.post(f"/sessions/{session_id}/calibration", data={"click_at_s": str(CLICK_AT_S)}, files=files)
    finally:
        for _, handle, _ in files.values():
            handle.close()


def test_notes_ten_cents_sharp_give_ten_cent_offset(client, violin_session, tmp_path):
    response = post_calibration(client, violin_session, tmp_path, cents=(10, 10, 10))
    assert response.status_code == 200
    profile = response.json()["profile"]
    assert profile["source"] == "live" and profile["calibrated"] is True
    assert profile["pitch_offset_cents"] == pytest.approx(10, abs=2)
    assert profile["noise_floor_db"] == pytest.approx(BACKGROUND_DB, abs=3)
    assert profile["pickup_db"] == {"low": pytest.approx(0, abs=1), "mid": 0, "high": pytest.approx(0, abs=1)}
    assert [n["asked"] for n in profile["notes"]] == ["D4", "A4", "E5"]
    assert all(n["problem"] is None for n in profile["notes"])
    assert profile["instrument_offset_cents"] is None
    assert store.get(violin_session).calibration == profile
    assert client.get(f"/sessions/{violin_session}/calibration").json() == {"profile": profile}


def test_latency_is_click_onset_minus_click_at(client, violin_session, tmp_path):
    profile = post_calibration(client, violin_session, tmp_path, latency_s=0.12).json()["profile"]
    assert profile["latency_ms"] == pytest.approx(120, abs=15)


def test_latency_is_clamped_to_zero_to_500(client, violin_session, tmp_path):
    profile = post_calibration(client, violin_session, tmp_path, latency_s=0.9).json()["profile"]
    assert profile["latency_ms"] == 500


def test_pickup_is_each_notes_level_relative_to_the_middle_note(client, violin_session, tmp_path):
    clips = [make_note_clip(tmp_path / f"loud_{i}.wav", note.hz, amplitude=amp)
             for i, (note, amp) in enumerate(zip(REFERENCE_NOTES["violin"], (0.3, 0.15, 0.3)))]
    pickup = post_calibration(client, violin_session, tmp_path, clips=clips).json()["profile"]["pickup_db"]
    assert pickup["low"] == pytest.approx(6, abs=1) and pickup["mid"] == 0 and pickup["high"] == pytest.approx(6, abs=1)


def test_webm_clips_are_decoded(client, violin_session, tmp_path):
    clips = [to_webm(make_note_clip(tmp_path / f"w{i}.wav", note.hz)) for i, note in enumerate(REFERENCE_NOTES["violin"])]
    files = {f"ref_{i}": (clip.name, clip.open("rb"), "audio/webm;codecs=opus") for i, clip in enumerate(clips)}
    click = make_click_clip(tmp_path / "click.wav", CLICK_AT_S, 0.1)
    files["click"] = (click.name, click.open("rb"), "audio/wav")
    response = client.post(f"/sessions/{violin_session}/calibration", data={"click_at_s": "0.5"}, files=files)
    assert response.status_code == 200
    assert response.json()["profile"]["pitch_offset_cents"] == pytest.approx(0, abs=3)


def test_off_pitch_note_fails_and_saves_nothing(client, violin_session, tmp_path):
    response = post_calibration(client, violin_session, tmp_path, cents=(0, 70, 0))
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "calibration_failed"
    assert body["error"]["message"] == "A4 was 70 cents off: is the tone page playing A4?"
    assert [(n["asked"], n["problem"]) for n in body["notes"]] == [("A4", "off_pitch")]
    assert body["notes"][0]["cents"] == pytest.approx(70, abs=3)
    assert store.get(violin_session).calibration is None


def test_silent_clip_is_not_heard(client, violin_session, tmp_path):
    clips = [make_note_clip(tmp_path / f"r{i}.wav", note.hz, silent=(i == 0)) for i, note in enumerate(REFERENCE_NOTES["violin"])]
    body = post_calibration(client, violin_session, tmp_path, clips=clips).json()
    assert body["error"]["code"] == "calibration_failed"
    assert body["notes"] == [{"asked": "D4", "problem": "not_heard", "cents": None}]
    assert "D4" in body["error"]["message"]


def test_loud_noise_is_too_noisy(client, violin_session, tmp_path):
    clips = [make_note_clip(tmp_path / f"r{i}.wav", note.hz, noise_db=-22 if i == 2 else BACKGROUND_DB)
             for i, note in enumerate(REFERENCE_NOTES["violin"])]
    body = post_calibration(client, violin_session, tmp_path, clips=clips).json()
    assert [(n["asked"], n["problem"]) for n in body["notes"]] == [("E5", "too_noisy")]
    assert store.get(violin_session).calibration is None


def test_every_failing_note_is_listed(client, violin_session, tmp_path):
    body = post_calibration(client, violin_session, tmp_path, cents=(70, 0, -70)).json()
    assert [(n["asked"], n["problem"]) for n in body["notes"]] == [("D4", "off_pitch"), ("E5", "off_pitch")]


def test_instrument_clips_give_instrument_offset(client, violin_session, tmp_path):
    inst = {f"inst_{i}": make_note_clip(tmp_path / f"inst_{i}.wav", note.hz, cents=20)
            for i, note in enumerate(REFERENCE_NOTES["violin"])}
    profile = post_calibration(client, violin_session, tmp_path, **inst).json()["profile"]
    assert profile["instrument_offset_cents"] == pytest.approx(20, abs=2)


def test_bad_instrument_clips_never_fail_the_calibration(client, violin_session, tmp_path):
    inst = {"inst_0": make_note_clip(tmp_path / "inst_0.wav", 293.66, silent=True)}
    response = post_calibration(client, violin_session, tmp_path, **inst)
    assert response.status_code == 200
    assert response.json()["profile"]["instrument_offset_cents"] is None


def test_unknown_session_is_404(client, tmp_path):
    assert_error(post_calibration(client, "nosuchsession", tmp_path), 404, "session_not_found")


def test_unsupported_clip_type_is_415(client, violin_session, tmp_path):
    clips = [make_note_clip(tmp_path / f"r{i}.wav", n.hz) for i, n in enumerate(REFERENCE_NOTES["violin"])]
    files = {f"ref_{i}": (c.name, c.open("rb"), "image/png") for i, c in enumerate(clips)}
    click = make_click_clip(tmp_path / "click.wav", CLICK_AT_S, 0.1)
    files["click"] = (click.name, click.open("rb"), "audio/wav")
    response = client.post(f"/sessions/{violin_session}/calibration", data={"click_at_s": "0.5"}, files=files)
    assert_error(response, 415, "unsupported_type")


def test_garbage_audio_is_unreadable(client, violin_session, tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not audio at all")
    clips = [bad] + [make_note_clip(tmp_path / f"r{i}.wav", n.hz) for i, n in enumerate(REFERENCE_NOTES["violin"]) if i]
    assert_error(post_calibration(client, violin_session, tmp_path, clips=clips), 422, "audio_unreadable")


def test_missing_click_or_bad_click_at_is_bad_request(client, violin_session, tmp_path):
    clip = make_note_clip(tmp_path / "r.wav", 293.66)
    files = {f"ref_{i}": (clip.name, clip.open("rb"), "audio/wav") for i in range(3)}
    assert_error(client.post(f"/sessions/{violin_session}/calibration", data={"click_at_s": "0.5"}, files=files),
                 422, "bad_request")
    click = make_click_clip(tmp_path / "click.wav", CLICK_AT_S, 0.1)
    files["click"] = (click.name, click.open("rb"), "audio/wav")
    assert_error(client.post(f"/sessions/{violin_session}/calibration", data={"click_at_s": "soon"}, files=files),
                 422, "bad_request")


def test_skip_saves_default_profile(client, violin_session):
    response = client.post(f"/sessions/{violin_session}/calibration/skip", json={})
    profile = response.json()["profile"]
    assert response.status_code == 200
    assert profile["source"] == "default" and profile["calibrated"] is False
    assert profile["pitch_offset_cents"] == 0 and profile["noise_floor_db"] == -60 and profile["latency_ms"] == 0
    assert profile["pickup_db"] == {"low": 0, "mid": 0, "high": 0} and profile["instrument_offset_cents"] is None
    assert store.get(violin_session).calibration == profile


def test_get_calibration_before_any_is_null(client, violin_session):
    assert client.get(f"/sessions/{violin_session}/calibration").json() == {"profile": None}


def test_skip_and_get_on_unknown_session_are_404(client):
    assert_error(client.post("/sessions/nosuchsession/calibration/skip", json={}), 404, "session_not_found")
    assert_error(client.get("/sessions/nosuchsession/calibration"), 404, "session_not_found")


@pytest.mark.parametrize("instrument,names", [("violin", ["D4", "A4", "E5"]), ("trumpet", ["Bb3", "F4", "Bb4"])])
def test_reference_notes_are_three_per_instrument(client, instrument, names):
    notes = client.get("/reference-notes", params={"instrument": instrument}).json()
    assert [n["name"] for n in notes] == names


def test_reference_note_frequencies(client):
    violin = client.get("/reference-notes?instrument=violin").json()
    trumpet = client.get("/reference-notes?instrument=trumpet").json()
    assert [n["hz"] for n in violin] == [293.66, 440.0, 659.26]
    assert [n["hz"] for n in trumpet] == [233.08, 349.23, 466.16]


def test_unknown_reference_instrument_is_bad_request(client):
    assert_error(client.get("/reference-notes?instrument=kazoo"), 422, "bad_request")
    assert_error(client.get("/reference-notes"), 422, "bad_request")


def test_trumpet_calibration_uses_trumpet_notes(client, tmp_path):
    session_id = client.post("/sessions", json={"instrument": "trumpet"}).json()["session_id"]
    profile = post_calibration(client, session_id, tmp_path, instrument="trumpet", cents=(5, 5, 5)).json()["profile"]
    assert [n["asked"] for n in profile["notes"]] == ["Bb3", "F4", "Bb4"]
    assert profile["pitch_offset_cents"] == pytest.approx(5, abs=2)
