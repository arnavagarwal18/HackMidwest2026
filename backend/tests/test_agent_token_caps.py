"""Each feedback agent asks Bedrock for a modest max_tokens, since the daily quota is charged by that cap."""
import pytest

from app.agents.coach import COACH_MAX_TOKENS, build_coach_agent
from app.agents.config import Settings
from app.agents.holder import RunHolder
from app.agents.model import build_agent_model
from app.agents.orchestrator import ORCHESTRATOR_MAX_TOKENS, build_orchestrator
from app.agents.planner import PLANNER_MAX_TOKENS, PLANNER_TOOLS, build_planner_agent
from app.agents.trace import Trace

SETTINGS = Settings(region="test-region", text_model="test-text", vision_model="test-vision", aws_profile="", ai_enabled=True)


@pytest.mark.parametrize("name, cap, builder", [
    ("coach", COACH_MAX_TOKENS, lambda m, c, h, t: build_coach_agent(m, [], c, h, t)),
    ("planner", PLANNER_MAX_TOKENS, lambda m, c, h, t: build_planner_agent(m, {n: (lambda: "") for n in PLANNER_TOOLS}, c, h, t)),
    ("orchestrator", ORCHESTRATOR_MAX_TOKENS, lambda m, c, h, t: build_orchestrator(m, {}, c, h, t)),
])
def test_each_agent_passes_its_cap_to_its_bedrock_model(name, cap, builder):
    shared = build_agent_model(SETTINGS)
    agent = builder(shared, None, RunHolder(), Trace())
    assert 500 <= cap <= 1500
    assert agent.model.get_config()["max_tokens"] == cap
    assert shared.get_config()["max_tokens"] == 2000  # the shared model, which the Instructor uses, is not changed
