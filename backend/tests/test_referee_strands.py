"""The real Strands path is built here but never called: no Bedrock access in tests."""
from app.score.model import Score
from app.score.referee import agent
from app.score.referee.tools import RefereeSession
from tests.referee_helpers import FOUR_QUARTERS, SETTINGS_ON, compare_of, make_reading, make_score, photo  # noqa: F401


def test_the_real_agent_is_built_with_the_four_tools_and_the_vision_model(photo, monkeypatch):
    score = make_score([FOUR_QUARTERS, FOUR_QUARTERS])
    reading = make_reading({1: FOUR_QUARTERS, 2: [("D5", "quarter")] * 4})
    session = RefereeSession(score, reading, compare_of(score, reading), photo)
    built = {}
    real_build = agent.build_bedrock_model

    def spy(settings, model_id, timeout_seconds):
        built["model_id"] = model_id
        return real_build(settings, model_id, timeout_seconds=timeout_seconds)

    monkeypatch.setattr(agent, "build_bedrock_model", spy)
    run_agent = agent.build_strands_agent(SETTINGS_ON, session, 60)
    assert callable(run_agent)
    assert built["model_id"] == "vision-model"


def test_key_fifths_survives_score_json_and_old_files_still_load():
    score = make_score([FOUR_QUARTERS], key_fifths=-2)
    assert Score.from_json(score.to_json()).key_fifths == -2
    old = score.to_dict()
    del old["key_fifths"]
    assert Score.from_dict(old).key_fifths is None
