import json

import pytest

from app import store
from app.takes import pipeline, pipeline_steps
from app.takes.take_store import add_take
from app.takes.transcribe import AudioUnreadable, NoNotesHeard, PlayedNote
from app.takes.validation import TakeRequest, new_take_fields
from tests.media_factory import make_wav

NOTE = PlayedNote(i=0, onset_s=0.1, offset_s=0.6, midi_float=69.1, midi=69, cents_off=10.0, confidence=0.9, voiced_ratio=0.95)


@pytest.fixture
def session_id(sessions_root):
    return store.create("trumpet").session_id


def make_take(session_id, tmp_path, kind="mic"):
    request = TakeRequest(kind=kind, source="recorded", bar_from=1, bar_to=4, tempo_bpm=90, count_in_beats=4, downbeat_s=0.5)
    wav = make_wav(tmp_path / "a.wav")
    take = add_take(
        session_id,
        lambda take_id: new_take_fields(take_id, request, f"{take_id}_upload.wav"),
        lambda take: (store.session_dir(session_id) / take["file"]).write_bytes(wav.read_bytes()),
    )
    return take["take_id"]


def stored(session_id, take_id="t1"):
    return store.get(session_id).takes[take_id]


class Recorder:
    """Stub steps that log the take's (status, form_status) at the moment they run."""

    def __init__(self, session_id, take_id="t1", fail=()):
        self.session_id, self.take_id, self.fail, self.calls = session_id, take_id, set(fail), []
        self.feedback_calls = []

    def _step(self, name):
        take = stored(self.session_id, self.take_id)
        self.calls.append((name, take["status"], take["form_status"]))
        if name in self.fail:
            raise RuntimeError(f"{name} stub failed")

    def transcriber(self, wav_path, instrument, profile, calib_end_s):
        self._step("transcribe")
        self.profile, self.calib_end_s, self.instrument = profile, calib_end_s, instrument
        return [NOTE]

    def diagnose(self, session_id, take_id):
        self._step("diagnose")

    def check_form(self, session_id, take_id):
        self._step("form")

    def give_feedback(self, session_id, take_id):
        self.feedback_calls.append((session_id, take_id, stored(session_id, take_id)["status"]))

    def run(self):
        pipeline.run_take_pipeline(self.session_id, self.take_id, transcriber=self.transcriber, diagnose=self.diagnose,
                                   check_form=self.check_form, give_feedback=self.give_feedback)


def test_mic_take_goes_processing_transcribed_diagnosed_done(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert recorder.calls == [("transcribe", "processing", "none"), ("diagnose", "transcribed", "none")]
    take = stored(session_id)
    assert (take["status"], take["error"], take["form_status"]) == ("done", None, "none")
    assert take["notes"] == [NOTE.to_dict()]


def test_status_changes_are_recorded_in_order(session_id, tmp_path, monkeypatch):
    statuses = []
    real_update = pipeline.update_take
    take_id = make_take(session_id, tmp_path, kind="video")

    def recording_update(sid, tid, **changes):
        real_update(sid, tid, **changes)
        statuses.append((changes.get("status"), changes.get("form_status")))

    monkeypatch.setattr(pipeline, "update_take", recording_update)
    monkeypatch.setattr(pipeline_steps, "update_take", recording_update)
    Recorder(session_id, take_id).run()
    assert [s for s in statuses if s != (None, None)] == [
        ("transcribed", None), ("diagnosed", None), (None, "processing"), (None, "done"), ("done", None),
    ]


def test_notes_are_saved_in_session_folder(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    Recorder(session_id, take_id).run()
    saved = json.loads((store.session_dir(session_id) / "t1_notes.json").read_text())
    assert saved == [NOTE.to_dict()]


def test_video_take_runs_form_then_done(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path, kind="video")
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert recorder.calls == [
        ("transcribe", "processing", "none"), ("diagnose", "transcribed", "none"), ("form", "diagnosed", "processing"),
    ]
    assert (stored(session_id)["status"], stored(session_id)["form_status"]) == ("done", "done")


def test_failing_form_leaves_take_done(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path, kind="video")
    Recorder(session_id, take_id, fail={"form"}).run()
    take = stored(session_id)
    assert (take["status"], take["error"], take["form_status"]) == ("done", None, "failed")


def test_mic_take_never_runs_form(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert "form" not in [call[0] for call in recorder.calls]


def test_unexpected_transcriber_error_is_transcription_failed(session_id, tmp_path, caplog):
    take_id = make_take(session_id, tmp_path)
    Recorder(session_id, take_id, fail={"transcribe"}).run()
    take = stored(session_id)
    assert (take["status"], take["error"]) == ("failed", "transcription_failed")
    assert "transcribe stub failed" in caplog.text


@pytest.mark.parametrize("error, code", [
    (NoNotesHeard("silence"), "no_notes_heard"),
    (AudioUnreadable("garbled"), "decode_failed"),
])
def test_known_transcriber_errors_map_to_codes(session_id, tmp_path, error, code):
    take_id = make_take(session_id, tmp_path)

    def transcriber(*args):
        raise error

    pipeline.run_take_pipeline(session_id, take_id, transcriber=transcriber)
    assert (stored(session_id)["status"], stored(session_id)["error"]) == ("failed", code)


def test_failing_diagnosis_fails_take(session_id, tmp_path, caplog):
    take_id = make_take(session_id, tmp_path)
    Recorder(session_id, take_id, fail={"diagnose"}).run()
    take = stored(session_id)
    assert (take["status"], take["error"]) == ("failed", "diagnosis_failed")
    assert take["notes"] == [NOTE.to_dict()]
    assert "diagnose stub failed" in caplog.text


def test_failing_diagnosis_skips_form(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path, kind="video")
    recorder = Recorder(session_id, take_id, fail={"diagnose"})
    recorder.run()
    assert [call[0] for call in recorder.calls] == ["transcribe", "diagnose"]
    assert stored(session_id)["form_status"] == "none"


def test_extraction_error_keeps_its_code(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    (store.session_dir(session_id) / "t1_upload.wav").write_bytes(b"not audio" * 50)
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert (stored(session_id)["status"], stored(session_id)["error"]) == ("failed", "decode_failed")
    assert recorder.calls == []


def test_default_profile_when_session_not_calibrated(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert recorder.profile == pipeline_steps.DEFAULT_PROFILE
    assert recorder.profile["pitch_offset_cents"] == 0 and recorder.profile["noise_floor_db"] == -60
    assert (recorder.calib_end_s, recorder.instrument) == (0.0, "trumpet")
    assert stored(session_id)["calibrated"] is False


def test_session_calibration_is_used(session_id, tmp_path):
    calibration = {**pipeline_steps.DEFAULT_PROFILE, "source": "mic", "calibrated": True, "pitch_offset_cents": -12}
    store.update(session_id, "calibration", calibration)
    take_id = make_take(session_id, tmp_path)
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert recorder.profile == calibration
    assert stored(session_id)["calibrated"] is True


def test_recorded_takes_are_not_calibrated_from_their_video(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path, kind="video")
    assert pipeline_steps.calibrate_from_video(session_id, take_id) == (None, 0.0)


def test_missing_steps_are_skipped_with_warning(session_id, tmp_path, caplog, monkeypatch):
    monkeypatch.setattr(pipeline_steps, "transcribe", lambda *args: [NOTE])
    take_id = make_take(session_id, tmp_path, kind="video")
    pipeline.run_take_pipeline(session_id, take_id)
    take = stored(session_id)
    assert (take["status"], take["error"], take["form_status"]) == ("done", None, "none")
    assert "app.diagnosis.run is not available" in caplog.text
    assert "app.form.run is not available" in caplog.text


def test_lazy_steps_are_found_when_modules_define_run(session_id, tmp_path, monkeypatch):
    import app.diagnosis
    import app.form

    calls = []
    monkeypatch.setattr(app.diagnosis, "run", lambda s, t: calls.append("diagnosis"), raising=False)
    monkeypatch.setattr(app.form, "run", lambda s, t: calls.append("form"), raising=False)
    monkeypatch.setattr(pipeline_steps, "transcribe", lambda *args: [NOTE])
    take_id = make_take(session_id, tmp_path, kind="video")
    pipeline.run_take_pipeline(session_id, take_id)
    assert calls == ["diagnosis", "form"]
    assert (stored(session_id)["status"], stored(session_id)["form_status"]) == ("done", "done")


def test_broken_import_inside_step_module_is_not_hidden(monkeypatch):
    def broken_import(name):
        raise ModuleNotFoundError("No module named 'numpyy'", name="numpyy")

    monkeypatch.setattr(pipeline_steps.importlib, "import_module", broken_import)
    with pytest.raises(ModuleNotFoundError):
        pipeline_steps.resolve_step("app.diagnosis")


def test_feedback_runs_after_diagnosis_and_form_for_a_take_then_the_take_is_done(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path, kind="video")
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert recorder.feedback_calls == [(session_id, take_id, "diagnosed")]
    assert [call[0] for call in recorder.calls] == ["transcribe", "diagnose", "form"]
    assert stored(session_id, take_id)["status"] == "done"


def test_feedback_is_skipped_for_other_purposes(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    pipeline.update_take(session_id, take_id, purpose="exercise")
    recorder = Recorder(session_id, take_id)
    recorder.run()
    assert recorder.feedback_calls == []
    assert stored(session_id, take_id)["status"] == "done"


def test_a_failed_take_gets_no_feedback(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)
    recorder = Recorder(session_id, take_id, fail={"diagnose"})
    recorder.run()
    assert recorder.feedback_calls == []
    assert stored(session_id, take_id)["status"] == "failed"


def test_a_take_whose_feedback_could_not_be_saved_stays_failed(session_id, tmp_path):
    take_id = make_take(session_id, tmp_path)

    def unsavable(sid, tid):
        pipeline.update_take(sid, tid, status="failed", error="storage_error")

    pipeline.run_take_pipeline(session_id, take_id, transcriber=lambda *args: [NOTE], diagnose=lambda s, t: None, give_feedback=unsavable)
    assert (stored(session_id, take_id)["status"], stored(session_id, take_id)["error"]) == ("failed", "storage_error")


def test_the_real_feedback_step_is_found_by_default(session_id, tmp_path, monkeypatch):
    from app.agents import run as feedback_run

    monkeypatch.setattr(feedback_run, "ai_enabled", lambda: False)
    monkeypatch.setattr(pipeline_steps, "transcribe", lambda *args: [NOTE])
    take_id = make_take(session_id, tmp_path)
    pipeline.run_take_pipeline(session_id, take_id)
    session = store.get(session_id)
    assert session.takes[take_id]["status"] == "done"
    assert [f["take_id"] for f in session.feedback.values()] == [take_id]
