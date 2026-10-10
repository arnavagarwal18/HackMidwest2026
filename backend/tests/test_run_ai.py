import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError

from app import store
from app.agents import ai_run, run
from tests.feedback_helpers import add_diagnosed_take
from tests.fake_model import ScriptedModel, sleep_turn, text_turn, tool_turn
from tests.test_checker_feedback import LATE_TEXT, sentence
from tests.test_coach_hook import submit, wrong_sentence

OVERVIEW = tool_turn("get_take_overview", {})
BRIEF = tool_turn("coach", {"brief": "Take t1, tier 1 problems p:t1:0 and p:t1:1, violin."})
ACCESS_DENIED = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "not allowed"}}, "ConverseStream")


@pytest.fixture(autouse=True)
def ai_on(monkeypatch):
    monkeypatch.setattr(run, "ai_enabled", lambda: True)


def use_script(monkeypatch, *script):
    model = ScriptedModel(script)
    monkeypatch.setattr(ai_run, "new_model", lambda: model)
    return model


def feedback_of(fixture_data, **diagnosis_changes):
    session_id, take_id = add_diagnosed_take(fixture_data, **diagnosis_changes)
    feedback_id = run.run_feedback(session_id, take_id)
    session = store.get(session_id)
    feedback = session.feedback[feedback_id]
    return feedback, session.plans[feedback["plan_id"]]


def test_the_ai_path_saves_checked_coach_sentences(sessions_root, fixture_data, monkeypatch):
    model = use_script(monkeypatch, OVERVIEW, BRIEF, submit(sentence()), text_turn())
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("ai", None)
    [shown] = feedback["sentences"]
    assert (shown["text"], shown["checked"], shown["cites"]) == (LATE_TEXT, True, ["p:t1:1"])
    assert shown["jump"] == {"bar": 3, "time_s": None}
    assert feedback["dropped"] == []
    assert feedback["check"] == {"coach_tries": 1, "planner_tries": 0, "claims_checked": 4, "claims_failed": 0, "sentences_dropped": 0}
    assert plan["mode"] == "fallback" and len(plan["exercises"]) == 3  # the Planner comes later
    assert model.calls == 4


def test_a_dropped_sentence_is_listed_and_the_rest_shown(sessions_root, fixture_data, monkeypatch):
    two = submit(wrong_sentence(), sentence())
    use_script(monkeypatch, OVERVIEW, BRIEF, two, two, text_turn())
    feedback, _ = feedback_of(fixture_data)
    assert feedback["mode"] == "ai" and [s["text"] for s in feedback["sentences"]] == [LATE_TEXT]
    assert [d["text"] for d in feedback["dropped"]] == [wrong_sentence()["text"]]
    assert (feedback["check"]["coach_tries"], feedback["check"]["sentences_dropped"]) == (2, 1)


def test_when_the_checker_drops_every_sentence_the_mode_stays_ai(sessions_root, fixture_data, monkeypatch):
    bad = submit(wrong_sentence())
    use_script(monkeypatch, OVERVIEW, BRIEF, bad, bad, text_turn())
    feedback, _ = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["sentences"]) == ("ai", [])
    assert len(feedback["dropped"]) == 1


def test_a_coach_that_never_gets_accepted_falls_back_with_checker_rejected(sessions_root, fixture_data, monkeypatch):
    unfixable = submit(sentence(), problem_ids=("p:t1:9",))
    use_script(monkeypatch, OVERVIEW, BRIEF, unfixable, unfixable, text_turn())
    feedback, _ = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "checker_rejected")
    assert [s["mode"] for s in feedback["sentences"]] == ["fallback", "fallback"]
    assert feedback["check"]["coach_tries"] == 2


@pytest.mark.parametrize("error", [
    ACCESS_DENIED, NoCredentialsError(), EndpointConnectionError(endpoint_url="https://bedrock.example"),
], ids=lambda e: type(e).__name__)
def test_a_model_error_falls_back_with_model_error(sessions_root, fixture_data, monkeypatch, caplog, error):
    use_script(monkeypatch, error)
    feedback, plan = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "model_error")
    assert len(plan["exercises"]) == 3 and feedback["sentences"][0]["mode"] == "fallback"
    assert type(error).__name__ in caplog.text


def test_a_coach_failure_inside_the_orchestrator_is_a_model_error(sessions_root, fixture_data, monkeypatch):
    use_script(monkeypatch, OVERVIEW, BRIEF, ACCESS_DENIED, text_turn())
    feedback, _ = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "model_error")


def test_a_run_over_the_time_limit_falls_back_with_timeout(sessions_root, fixture_data, monkeypatch):
    monkeypatch.setattr(ai_run, "TIME_LIMIT_S", 0.2)
    use_script(monkeypatch, sleep_turn(5))
    feedback, _ = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "timeout")


def test_coach_output_accepted_before_a_timeout_is_kept(sessions_root, fixture_data, monkeypatch):
    monkeypatch.setattr(ai_run, "TIME_LIMIT_S", 0.5)
    use_script(monkeypatch, OVERVIEW, BRIEF, submit(sentence()), sleep_turn(5))
    feedback, _ = feedback_of(fixture_data)
    assert (feedback["mode"], feedback["fallback_reason"], len(feedback["sentences"])) == ("ai", None, 1)


def test_a_take_that_cant_be_judged_never_calls_the_model(sessions_root, fixture_data, monkeypatch):
    def forbidden():
        raise AssertionError("the model must not be built")

    monkeypatch.setattr(ai_run, "new_model", forbidden)
    feedback, _ = feedback_of(fixture_data, cant_tell=True)
    assert (feedback["mode"], feedback["fallback_reason"]) == ("fallback", "cant_tell")
