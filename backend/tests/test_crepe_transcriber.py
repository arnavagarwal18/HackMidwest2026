import logging

import numpy as np
import pytest
import soundfile as sf

from app.takes import crepe_pitch, pipeline_steps, transcriber
from app.takes.crepe_pitch import CrepeUnavailable
from app.takes.transcribe import NoNotesHeard, UnknownInstrument
from test_transcribe import MELODY, SAMPLE_RATE, make_melody


@pytest.fixture
def melody_wav(tmp_path):
    audio, _ = make_melody()
    path = tmp_path / "melody.wav"
    sf.write(path, audio, SAMPLE_RATE)
    return path


@pytest.fixture
def silent_wav(tmp_path):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(SAMPLE_RATE * 2, dtype=np.float32), SAMPLE_RATE)
    return path


def crepe_cannot_run(*args, **kwargs):
    raise CrepeUnavailable("CREPE is not installed")


def test_switch_defaults_to_pyin(monkeypatch):
    monkeypatch.delenv(transcriber.TRANSCRIBER_ENV, raising=False)
    assert transcriber.selected_transcriber() == "pyin"


@pytest.mark.parametrize("value, expected", [("crepe", "crepe"), ("CREPE", "crepe"), (" pyin ", "pyin")])
def test_switch_reads_the_setting(monkeypatch, value, expected):
    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, value)
    assert transcriber.selected_transcriber() == expected


def test_unknown_value_uses_pyin_and_logs_it(monkeypatch, caplog, melody_wav):
    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, "whisper")
    monkeypatch.setattr(crepe_pitch, "_predict", crepe_cannot_run)  # would raise if CREPE were tried
    with caplog.at_level(logging.ERROR, logger="app.takes.transcriber"):
        notes = transcriber.transcribe(melody_wav, "trumpet")
    assert "'whisper' is not 'pyin' or 'crepe'" in caplog.text
    assert [note.midi for note in notes] == MELODY


def test_pyin_mode_never_touches_crepe(monkeypatch, melody_wav):
    monkeypatch.delenv(transcriber.TRANSCRIBER_ENV, raising=False)
    monkeypatch.setattr(crepe_pitch, "_predict", crepe_cannot_run)
    assert [note.midi for note in transcriber.transcribe(melody_wav, "trumpet")] == MELODY


def test_crepe_mode_transcribes_sine_notes(monkeypatch, melody_wav):
    pytest.importorskip("crepe")
    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, "crepe")
    monkeypatch.setenv(crepe_pitch.CREPE_CAPACITY_ENV, "tiny")
    notes = transcriber.transcribe(melody_wav, "trumpet")
    assert [note.midi for note in notes] == MELODY
    assert all(abs(note.cents_off) < 30 for note in notes)


def test_crepe_that_cannot_run_falls_back_to_pyin_and_logs_it(monkeypatch, caplog, melody_wav):
    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, "crepe")
    monkeypatch.setattr(crepe_pitch, "_predict", crepe_cannot_run)
    with caplog.at_level(logging.ERROR, logger="app.takes.transcriber"):
        notes = transcriber.transcribe(melody_wav, "trumpet")
    assert "CREPE is not available; transcribing with pyin instead" in caplog.text
    assert [note.midi for note in notes] == MELODY


def test_crepe_crash_falls_back_to_pyin_and_logs_it(monkeypatch, caplog, melody_wav):
    def crash(*args, **kwargs):
        raise RuntimeError("model file corrupt")

    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, "crepe")
    monkeypatch.setattr(crepe_pitch, "_predict", crash)
    with caplog.at_level(logging.ERROR, logger="app.takes.transcriber"):
        notes = transcriber.transcribe(melody_wav, "trumpet")
    assert "CREPE failed on" in caplog.text and "model file corrupt" in caplog.text
    assert [note.midi for note in notes] == MELODY


def test_crepe_mode_with_no_sound_raises_no_notes_heard_instead_of_falling_back(monkeypatch, silent_wav):
    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, "crepe")
    monkeypatch.setattr(crepe_pitch, "_predict", lambda audio, capacity: (np.full(len(audio) // 160 + 1, 440.0),
                                                                          np.zeros(len(audio) // 160 + 1)))
    with pytest.raises(NoNotesHeard):
        transcriber.transcribe(silent_wav, "trumpet")


def test_crepe_mode_rejects_an_unknown_instrument(monkeypatch, melody_wav):
    monkeypatch.setenv(transcriber.TRANSCRIBER_ENV, "crepe")
    with pytest.raises(UnknownInstrument):
        transcriber.transcribe(melody_wav, "kazoo")


def test_unknown_capacity_uses_the_default_and_logs_it(monkeypatch, caplog):
    monkeypatch.setenv(crepe_pitch.CREPE_CAPACITY_ENV, "huge")
    with caplog.at_level(logging.ERROR, logger="app.takes.crepe_pitch"):
        assert crepe_pitch.model_capacity() == crepe_pitch.DEFAULT_CAPACITY
    assert "'huge'" in caplog.text


def test_the_pipeline_transcribes_through_the_switch():
    assert pipeline_steps.transcribe is transcriber.transcribe
