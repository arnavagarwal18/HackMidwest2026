"""A feedback module that can't be imported (strands, boto3...) must not fail the take or lose its other results."""
import importlib
import logging

import pytest

from app import store
from app.takes import pipeline, pipeline_steps
from app.takes.pipeline_steps import StepFailed
from tests.test_pipeline import NOTE, Recorder, make_take, stored

FEEDBACK_MODULE = "app.agents.run"
DIAGNOSIS = {"cant_tell": False, "problems": []}


@pytest.fixture
def session_id(sessions_root):
    return store.create("trumpet").session_id


@pytest.fixture
def feedback_import_fails(monkeypatch):
    real_import = importlib.import_module

    def import_module(name, *args, **kwargs):
        if name == FEEDBACK_MODULE:
            raise ImportError("No module named 'strands' (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(pipeline_steps.importlib, "import_module", import_module)


def test_resolving_the_feedback_step_raises_feedback_unavailable(feedback_import_fails, caplog):
    with caplog.at_level(logging.ERROR, logger="app.takes.pipeline"):
        with pytest.raises(StepFailed) as raised:
            pipeline_steps.resolve_feedback_step()
    assert raised.value.code == "feedback_unavailable"
    assert "could not be imported" in caplog.text


def test_other_steps_still_re_raise_import_errors(feedback_import_fails):
    with pytest.raises(ImportError):
        pipeline_steps.resolve_step(FEEDBACK_MODULE, "run_feedback")


def test_take_is_done_with_diagnosis_and_form_but_no_feedback(session_id, tmp_path, feedback_import_fails, caplog, client):
    take_id = make_take(session_id, tmp_path, kind="video")
    recorder = Recorder(session_id, take_id)
    recorder.diagnose = lambda s, t: pipeline.update_take(s, t, diagnosis=DIAGNOSIS)
    recorder.check_form = lambda s, t: pipeline.update_take(s, t, form={"flags": []}, form_status="done")

    with caplog.at_level(logging.WARNING, logger="app.takes.pipeline"):
        pipeline.run_take_pipeline(session_id, take_id, transcriber=recorder.transcriber, diagnose=recorder.diagnose,
                                   check_form=recorder.check_form)

    take = stored(session_id, take_id)
    assert (take["status"], take["error"], take["form_status"]) == ("done", None, "done")
    assert take["notes"] == [NOTE.to_dict()]
    assert take["diagnosis"] == DIAGNOSIS
    assert take["form"] == {"flags": []}
    assert store.get(session_id).feedback == {} and store.get(session_id).plans == {}
    assert any(r.levelno == logging.WARNING and "feedback_unavailable" in r.getMessage() for r in caplog.records)

    response = client.get(f"/sessions/{session_id}/takes/{take_id}/feedback")
    assert (response.status_code, response.json()["error"]["code"]) == (409, "wrong_state")


def test_a_rep_take_never_looks_for_feedback(session_id, tmp_path, feedback_import_fails):
    take_id = make_take(session_id, tmp_path)
    pipeline.update_take(session_id, take_id, purpose="rep")
    recorder = Recorder(session_id, take_id)
    pipeline.run_take_pipeline(session_id, take_id, transcriber=recorder.transcriber, diagnose=recorder.diagnose,
                               check_form=recorder.check_form, score=lambda s, t: None)
    assert stored(session_id, take_id)["status"] == "done"
