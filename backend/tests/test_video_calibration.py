"""Calibration from an uploaded video: reference notes at its start give a 'video' profile and are cut from the take."""
import numpy as np
import pytest
import soundfile as sf

from app import store
from app.takes import calibrate, pipeline, pipeline_steps, video_calibration
from app.takes.take_store import add_take
from app.takes.reference import reference_notes
from app.takes.validation import TakeRequest, new_take_fields
from tests.media_factory import make_video_with_audio

SAMPLE_RATE = 16000
LEAD_IN_S, NOTE_S, GAP_S = 0.5, 1.0, 0.5
VIOLIN_MELODY = [67, 71, 72]  # G4, B4, C5: none of them a reference note
LEVEL_DB_NOISE = -55


def midi_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def tone(hz, seconds, amplitude=0.3):
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    envelope = np.minimum(1.0, np.minimum(t, seconds - t) / 0.02)
    return amplitude * envelope * np.sin(2 * np.pi * hz * t)


def build_audio(tones, tail_s=0.5):
    """Silence, then each (hz, amplitude) as a one second note followed by a gap; returns (audio, [(start_s, end_s)])."""
    pieces, spans, cursor = [np.zeros(int(LEAD_IN_S * SAMPLE_RATE))], [], LEAD_IN_S
    for hz, amplitude in tones:
        pieces += [tone(hz, NOTE_S, amplitude), np.zeros(int(GAP_S * SAMPLE_RATE))]
        spans.append((cursor, cursor + NOTE_S))
        cursor += NOTE_S + GAP_S
    pieces.append(np.zeros(int(tail_s * SAMPLE_RATE)))
    audio = np.concatenate(pieces)
    noise = np.random.default_rng(0).normal(0, 10 ** (LEVEL_DB_NOISE / 20), size=audio.shape)
    return (audio + noise).astype(np.float32), spans


def reference_tones(shift_cents=0.0, amplitudes=(0.3, 0.3, 0.3)):
    return [(note.hz * 2 ** (shift_cents / 1200), a) for note, a in zip(reference_notes("violin"), amplitudes)]


def melody_tones():
    return [(midi_hz(midi), 0.3) for midi in VIOLIN_MELODY]


def make_take(session_id, tmp_path, tones, source="uploaded", suffix=".mp4"):
    audio, spans = build_audio(tones)
    wav = tmp_path / "audio.wav"
    sf.write(wav, audio, SAMPLE_RATE)
    video = make_video_with_audio(tmp_path / f"video{suffix}", wav)
    request = TakeRequest(kind="video", source=source, bar_from=1, bar_to=4, tempo_bpm=90, count_in_beats=4,
                          downbeat_s=0.5 if source == "recorded" else None)
    take = add_take(
        session_id,
        lambda take_id: new_take_fields(take_id, request, f"{take_id}{suffix}"),
        lambda take: (store.session_dir(session_id) / take["file"]).write_bytes(video.read_bytes()),
    )
    return take["take_id"], spans


def run_pipeline(session_id, take_id):
    noop = lambda *_: None
    pipeline.run_take_pipeline(session_id, take_id, diagnose=noop, check_form=noop)
    return store.get(session_id).takes[take_id]


def calibrate_extracted(session_id, take_id):
    """The calibration step alone: extract the take's audio, then calibrate from it."""
    pipeline.extract_audio(session_id, take_id)
    return pipeline_steps.calibrate_from_video(session_id, take_id)


@pytest.fixture
def session_id(sessions_root):
    return store.create("violin").session_id


@pytest.mark.parametrize("suffix", [".mp4", ".webm"])
def test_reference_notes_calibrate_and_are_cut_from_the_take(session_id, tmp_path, suffix):
    take_id, spans = make_take(session_id, tmp_path, reference_tones() + melody_tones(), suffix=suffix)
    take = run_pipeline(session_id, take_id)
    third_note_end_s, melody_start_s = spans[2][1], spans[3][0]
    assert take["status"] == "done" and take["error"] is None
    assert take["calibrated"] is True
    assert third_note_end_s <= take["calib_end_s"] < melody_start_s
    assert [n["midi"] for n in take["notes"]] == VIOLIN_MELODY
    assert all(n["onset_s"] >= take["calib_end_s"] for n in take["notes"])


def test_profile_is_built_from_the_reference_notes_and_not_stored_on_the_session(session_id, tmp_path):
    take_id, spans = make_take(session_id, tmp_path, reference_tones(shift_cents=20, amplitudes=(0.3, 0.15, 0.3)))
    profile, calib_end_s = calibrate_extracted(session_id, take_id)
    assert profile["source"] == "video" and profile["calibrated"] is True
    assert profile["pitch_offset_cents"] == pytest.approx(20, abs=3)
    assert profile["latency_ms"] == 0 and profile["instrument_offset_cents"] is None
    assert profile["pickup_db"]["low"] == pytest.approx(6, abs=1.5) and profile["pickup_db"]["mid"] == 0
    assert profile["pickup_db"]["high"] == pytest.approx(6, abs=1.5)
    assert profile["noise_floor_db"] < -40
    assert [n["asked"] for n in profile["notes"]] == ["D4", "A4", "E5"]
    assert all(n["problem"] is None for n in profile["notes"])
    assert spans[2][1] <= calib_end_s < spans[2][1] + 0.3
    assert store.get(session_id).calibration is None


def test_video_without_reference_notes_is_not_calibrated(session_id, tmp_path):
    take_id, _ = make_take(session_id, tmp_path, melody_tones())
    take = run_pipeline(session_id, take_id)
    assert (take["calibrated"], take["calib_end_s"], take["status"]) == (False, 0, "done")
    assert [n["midi"] for n in take["notes"]] == VIOLIN_MELODY
    assert store.get(session_id).calibration is None


def test_two_reference_notes_are_not_enough(session_id, tmp_path):
    take_id, _ = make_take(session_id, tmp_path, reference_tones()[:2] + melody_tones())
    assert calibrate_extracted(session_id, take_id) == (None, 0.0)


def test_reference_notes_out_of_order_are_not_found(session_id, tmp_path):
    take_id, _ = make_take(session_id, tmp_path, reference_tones()[::-1] + melody_tones())
    assert calibrate_extracted(session_id, take_id) == (None, 0.0)


def test_reference_notes_more_than_50_cents_off_are_not_found(session_id, tmp_path):
    take_id, _ = make_take(session_id, tmp_path, reference_tones(shift_cents=70) + melody_tones())
    assert calibrate_extracted(session_id, take_id) == (None, 0.0)


def test_reference_notes_shorter_than_half_a_second_are_not_found():
    audio = np.concatenate([np.zeros(SAMPLE_RATE // 2)] + [
        np.concatenate([tone(note.hz, 0.4), np.zeros(SAMPLE_RATE // 2)]) for note in reference_notes("violin")
    ]).astype(np.float32)
    assert video_calibration.calibrate_from_audio(audio, "violin") == (None, 0.0)


def test_reference_notes_after_the_first_20_seconds_are_not_found():
    audio = np.concatenate([np.zeros(21 * SAMPLE_RATE), build_audio(reference_tones())[0]]).astype(np.float32)
    assert video_calibration.calibrate_from_audio(audio, "violin") == (None, 0.0)


def test_noisy_reference_notes_are_not_used(session_id, tmp_path, caplog):
    audio, _ = build_audio(reference_tones(amplitudes=(0.3, 0.3, 0.3)))
    audio = audio + np.random.default_rng(1).normal(0, 0.06, size=audio.shape).astype(np.float32)
    assert video_calibration.calibrate_from_audio(audio, "violin") == (None, 0.0)
    assert "not usable for calibration" in caplog.text


def test_recorded_take_skips_video_calibration(session_id, tmp_path, monkeypatch):
    monkeypatch.setattr(video_calibration, "calibrate_from_audio", lambda *_: pytest.fail("should be skipped"))
    take_id, _ = make_take(session_id, tmp_path, reference_tones() + melody_tones(), source="recorded")
    take = run_pipeline(session_id, take_id)
    assert (take["calibrated"], take["calib_end_s"], take["status"]) == (False, 0, "done")
    assert [n["midi"] for n in take["notes"]][:3] == [62, 69, 76]


def test_live_session_profile_skips_video_calibration(session_id, tmp_path, monkeypatch):
    live = {**calibrate.default_profile(), "source": "live", "calibrated": True, "pitch_offset_cents": -7.0}
    store.update(session_id, "calibration", live)
    monkeypatch.setattr(pipeline_steps, "calibrate_from_audio", lambda *_: pytest.fail("should be skipped"))
    take_id, _ = make_take(session_id, tmp_path, reference_tones() + melody_tones())
    take = run_pipeline(session_id, take_id)
    assert (take["calibrated"], take["calib_end_s"]) == (True, 0)
    assert store.get(session_id).calibration == live


def test_skipped_session_profile_still_tries_video_calibration(session_id, tmp_path):
    store.update(session_id, "calibration", calibrate.default_profile())
    take_id, _ = make_take(session_id, tmp_path, reference_tones() + melody_tones())
    take = run_pipeline(session_id, take_id)
    assert take["calibrated"] is True and take["calib_end_s"] > 0
    assert store.get(session_id).calibration["source"] == "default"


def test_analysis_failure_is_logged_and_the_take_goes_on_uncalibrated(session_id, tmp_path, monkeypatch, caplog):
    def explode(*_):
        raise RuntimeError("analysis broke")

    monkeypatch.setattr(pipeline_steps, "calibrate_from_audio", explode)
    take_id, _ = make_take(session_id, tmp_path, reference_tones() + melody_tones())
    take = run_pipeline(session_id, take_id)
    assert (take["status"], take["calibrated"], take["calib_end_s"]) == ("done", False, 0)
    assert "Calibration from the video of take" in caplog.text
