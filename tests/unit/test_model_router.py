import pytest

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole
from engineering_team.llm.router import ModelRouter


@pytest.mark.parametrize(
    ("role", "profile", "model"),
    [
        (AgentRole.PRODUCT, "DEEP_MODEL", "qwen3.5:9b"),
        (AgentRole.ARCHITECTURE, "FAST_MODEL", "qwen3.5:4b"),
        (AgentRole.DEVELOPER, "CODING_MODEL", "qwen3.5:9b"),
        (AgentRole.SECURITY, "DEEP_MODEL", "qwen3.5:9b"),
        (AgentRole.TESTING, "FAST_MODEL", "qwen3.5:4b"),
        (AgentRole.REVIEWER, "DEEP_MODEL", "qwen3.5:9b"),
    ],
)
def test_local_role_mapping_is_fixed(role: AgentRole, profile: str, model: str) -> None:
    selection = ModelRouter(Settings(_env_file=None)).local_for(role)

    assert (selection.model_profile, selection.model) == (profile, model)


def test_router_has_no_agent_selected_override() -> None:
    router = ModelRouter(Settings(_env_file=None))
    assert router.local_for(AgentRole.SECURITY) == router.local_for(AgentRole.SECURITY)
