import pytest

from app.agents.prompts import COACH_PROMPT, ORCHESTRATOR_PROMPT, PLANNER_PROMPT


@pytest.mark.parametrize("prompt", [ORCHESTRATOR_PROMPT, COACH_PROMPT, PLANNER_PROMPT], ids=["orchestrator", "coach", "planner"])
def test_every_prompt_is_for_a_trumpet_learner_and_names_no_other_instrument(prompt):
    lowered = prompt.lower()
    assert "trumpet" in lowered
    for other in ("violin", "piano", "guitar", "instrument"):
        assert other not in lowered
