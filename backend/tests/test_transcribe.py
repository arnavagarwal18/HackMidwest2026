import numpy as np
import pytest
import soundfile as sf

from app.takes.transcribe import NoNotesHeard, UnknownInstrument, transcribe
from synth_audio import synthesize, write_wav as write_synth_wav

SAMPLE_RATE = 16000
BPM = 100
NOTE_S = 60 / BPM  # 0.6 s per beat
TONE_S = 0.5  # sounding part of each beat; the rest is a short gap
# A4, B4, C#5, D5, E5, F#5, G#5, A5
MELODY = [69, 71, 73, 74, 76, 78, 80, 81]


def midi_to_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def make_melody(midi_notes=MELODY, vibrato_cents=0.0, shift_cents=0.0, noise_db=None, lead_in_s=0.3):
    """Sine notes (one per beat) with optional 6 Hz vibrato, pitch shift and white noise; returns (audio, onsets)."""
    total = lead_in_s + NOTE_S * len(midi_notes) + 0.3
    t = np.arange(int(total * SAMPLE_RATE)) / SAMPLE_RATE
    audio = np.zeros_like(t)
    onsets = []
    for index, midi in enumerate(midi_notes):
        start = lead_in_s + index * NOTE_S
        onsets.append(start)
        mask = (t >= start) & (t < start + TONE_S)
        local = t[mask] - start
        cents = shift_cents + vibrato_cents * np.sin(2 * np.pi * 6 * local)
        freq = midi_to_hz(midi) * 2 ** (cents / 1200)
        phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
        envelope = np.minimum(1.0, np.minimum(local, TONE_S - local) / 0.02)
        audio[mask] = 0.4 * envelope * np.sin(phase)
    if noise_db is not None:
        rng = np.random.default_rng(0)
        audio += rng.normal(0, 10 ** (noise_db / 20), size=audio.shape)
    return audio.astype(np.float32), onsets


def write_wav(tmp_path, audio, name="take.wav"):
    path = tmp_path / name
    sf.write(path, audio, SAMPLE_RATE)
    return path


def assert_melody_found(notes, onsets):
    assert [n.midi for n in notes] == MELODY
    assert [n.i for n in notes] == list(range(len(MELODY)))
    for note, onset in zip(notes, onsets):
        assert abs(note.onset_s - onset) <= 0.03
        assert note.offset_s > note.onset_s


def test_eight_sine_notes(tmp_path):
    audio, onsets = make_melody()
    notes = transcribe(write_wav(tmp_path, audio), "trumpet", {})
    assert_melody_found(notes, onsets)
    assert all(abs(n.cents_off) < 5 for n in notes)
    assert all(0 <= n.confidence <= 1 and 0 < n.voiced_ratio <= 1 for n in notes)


def test_violin_range_and_default_profile(tmp_path):
    audio, onsets = make_melody()
    notes = transcribe(write_wav(tmp_path, audio), "violin", None)
    assert_melody_found(notes, onsets)


def test_vibrato_30_cents(tmp_path):
    audio, onsets = make_melody(vibrato_cents=30)
    notes = transcribe(write_wav(tmp_path, audio), "trumpet", {})
    assert_melody_found(notes, onsets)


def test_white_noise_found_with_lower_confidence(tmp_path):
    clean, onsets = make_melody()
    noisy, _ = make_melody(noise_db=-30)
    clean_notes = transcribe(write_wav(tmp_path, clean, "clean.wav"), "trumpet", {})
    noisy_notes = transcribe(write_wav(tmp_path, noisy, "noisy.wav"), "trumpet", {})
    assert_melody_found(noisy_notes, onsets)
    assert np.mean([n.confidence for n in noisy_notes]) < np.mean([n.confidence for n in clean_notes])


def test_pitch_offset_corrects_sharp_recording(tmp_path):
    audio, _ = make_melody(shift_cents=20)
    path = write_wav(tmp_path, audio)
    corrected = transcribe(path, "trumpet", {"pitch_offset_cents": 20})
    assert [n.midi for n in corrected] == MELODY
    assert all(abs(n.cents_off) <= 5 for n in corrected)
    uncorrected = transcribe(path, "trumpet", {})
    assert all(abs(n.cents_off - 20) <= 5 for n in uncorrected)


def test_calib_end_skips_start_and_keeps_raw_times(tmp_path):
    audio, onsets = make_melody()
    skip_s = onsets[2] - 0.1
    notes = transcribe(write_wav(tmp_path, audio), "trumpet", {}, calib_end_s=skip_s)
    assert [n.midi for n in notes] == MELODY[2:]
    assert abs(notes[0].onset_s - onsets[2]) <= 0.03


def test_silent_wav_raises_no_notes_heard(tmp_path):
    path = write_wav(tmp_path, np.zeros(2 * SAMPLE_RATE, dtype=np.float32))
    with pytest.raises(NoNotesHeard) as error:
        transcribe(path, "trumpet", {})
    assert error.value.code == "no_notes_heard"


def test_unknown_instrument_and_unreadable_file(tmp_path):
    audio, _ = make_melody()
    with pytest.raises(UnknownInstrument):
        transcribe(write_wav(tmp_path, audio), "kazoo", {})
    missing = tmp_path / "missing.wav"
    with pytest.raises(Exception) as error:
        transcribe(missing, "trumpet", {})
    assert error.value.code == "audio_unreadable"


def test_to_dict_has_spec_fields(tmp_path):
    audio, _ = make_melody()
    note = transcribe(write_wav(tmp_path, audio), "trumpet", {})[0]
    assert set(note.to_dict()) == {
        "i", "onset_s", "offset_s", "midi_float", "midi", "cents_off", "confidence", "voiced_ratio",
    }


def test_repeated_pitch_on_a_decaying_note_is_two_notes(tmp_path):
    """A note bowed again at the same pitch after a short gap, with the first one still fading, is two notes."""
    beats = [{"midi": midi, "onset_beats": beat, "dur_beats": 1} for beat, midi in enumerate([60, 60, 67, 67])]
    wav = write_synth_wav(tmp_path / "repeat.wav", synthesize(beats, NOTE_S, 1.0))
    notes = transcribe(wav, "violin", {})
    assert [n.midi for n in notes] == [60, 60, 67, 67]
    for note, beat in zip(notes, range(4)):
        assert abs(note.onset_s - (1.0 + beat * NOTE_S)) <= 0.05


def long_tone(midi, seconds, dip_at_s=None, dip_db=12.0, dip_s=0.2, vibrato_cents=0.0, tremolo_db=0.0):
    """One unbroken tone: optional smooth soft dip in level (a slurred or soft-tongued re-articulation), vibrato and tremolo."""
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    freq = midi_to_hz(midi) * 2 ** (vibrato_cents * np.sin(2 * np.pi * 5.5 * t) / 1200)
    gain_db = tremolo_db * np.sin(2 * np.pi * 5.5 * t)
    if dip_at_s is not None:
        gain_db = gain_db - dip_db * np.clip(1 - np.abs(t - dip_at_s) / (dip_s / 2), 0, 1)
    tone = 0.3 * 10 ** (gain_db / 20) * np.sin(2 * np.pi * np.cumsum(freq) / SAMPLE_RATE)
    envelope = np.minimum(1.0, np.minimum(t, seconds - t) / 0.03)
    padding = np.zeros(int(0.3 * SAMPLE_RATE))
    return np.concatenate([padding, tone * envelope, padding]).astype(np.float32)


def test_soft_dip_between_same_pitch_tones_is_two_notes(tmp_path):
    """Soft tonguing: the level sags and returns with no hard attack for librosa to catch; still two notes."""
    audio = long_tone(71, 1.4, dip_at_s=0.7, dip_db=8.0, dip_s=0.5)
    notes = transcribe(write_wav(tmp_path, audio), "trumpet", {})
    assert [n.midi for n in notes] == [71, 71]
    assert abs(notes[1].onset_s - (0.3 + 0.7)) <= 0.2


def test_steady_tone_with_vibrato_and_tremolo_is_one_note(tmp_path):
    audio = long_tone(71, 1.4, vibrato_cents=30, tremolo_db=1.5)
    notes = transcribe(write_wav(tmp_path, audio), "trumpet", {})
    assert [n.midi for n in notes] == [71]
