import pytest

from app import store
from app.takes import pipeline
from app.takes.transcribe import PlayedNote
from tests.practice_helpers import add_rep, add_take, exercise, save_plan

NOTE = PlayedNote(i=0, onset_s=0.1, offset_s=0.6, midi_float=69.1, midi=69, cents_off=10.0, confidence=0.9, voiced_ratio=0.95)


@pytest.fixture
def session_id(sessions_root, monkeypatch):
    sid = store.create("trumpet").session_id
    save_plan(sid, "pl1", exercise("ex1", 2, 3), exercise("ex2", 2, 3, form_rule="elbow"))
    monkeypatch.setattr(pipeline, "extract_audio", lambda *args: None)
    return sid


class Steps:
    def __init__(self, sid, take_id="t1", diagnose_fails=False):
        self.sid, self.take_id, self.diagnose_fails = sid, take_id, diagnose_fails
        self.calls = []

    def transcriber(self, *args):
        self.calls.append("transcribe")
        return [NOTE]

    def diagnose(self, sid, take_id):
        self.calls.append("diagnose")
        if self.diagnose_fails:
            pipeline.update_take(sid, take_id, status="failed", error="no_score")

    def check_form(self, sid, take_id):
        self.calls.append("form")

    def feedback(self, sid, take_id):
        self.calls.append("feedback")

    def score(self, sid, take_id):
        self.calls.append("score")

    def run(self):
        pipeline.run_take_pipeline(self.sid, self.take_id, transcriber=self.transcriber, diagnose=self.diagnose,
                                   check_form=self.check_form, give_feedback=self.feedback, score=self.score)


def test_a_mic_rep_is_transcribed_diagnosed_and_scored_without_the_agents(session_id):
    add_rep(session_id, "t1", status="processing")
    steps = Steps(session_id)
    steps.run()
    assert steps.calls == ["transcribe", "diagnose", "score"]
    assert store.get(session_id).takes["t1"]["status"] == "done"


def test_a_video_rep_runs_the_form_check_only_for_an_exercise_with_a_form_rule(session_id):
    add_rep(session_id, "t1", kind="video", exercise_id="ex2", status="processing")
    add_rep(session_id, "t2", kind="video", exercise_id="ex1", status="processing")
    with_rule, without_rule = Steps(session_id, "t1"), Steps(session_id, "t2")
    with_rule.run()
    without_rule.run()
    assert with_rule.calls == ["transcribe", "diagnose", "form", "score"]
    assert without_rule.calls == ["transcribe", "diagnose", "score"]


def test_a_rep_whose_diagnosis_failed_is_still_scored_so_the_failure_is_recorded(session_id):
    add_rep(session_id, "t1", status="processing")
    steps = Steps(session_id, diagnose_fails=True)
    steps.run()
    assert steps.calls == ["transcribe", "diagnose", "score"]
    assert store.get(session_id).takes["t1"]["status"] == "failed"


def test_a_normal_take_still_gets_feedback_and_is_not_scored(session_id):
    add_take(session_id, "t1", status="processing")
    steps = Steps(session_id)
    steps.run()
    assert steps.calls == ["transcribe", "diagnose", "feedback"]


def test_the_default_score_step_is_practice_score_rep(session_id, monkeypatch):
    add_rep(session_id, "t1", status="processing")
    scored = []
    monkeypatch.setattr(pipeline, "score_rep", lambda sid, take_id: scored.append(take_id))
    steps = Steps(session_id)
    pipeline.run_take_pipeline(session_id, "t1", transcriber=steps.transcriber, diagnose=steps.diagnose,
                               check_form=steps.check_form, give_feedback=steps.feedback)
    assert scored == ["t1"] and "feedback" not in steps.calls
