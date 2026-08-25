import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.runtime import LocalModelRuntime
from engineering_team.models.context import build_context


@pytest.mark.parametrize("role", list(AgentRole))
def test_consumed_system_prompt_declares_role_boundaries_evidence_and_authority(role) -> None:
    state = EngineeringState(run_id="prompt", requirement="safe bounded change")
    candidate = ProductAgent().execute(build_context(AgentRole.PRODUCT, state, "Product"))
    envelope = build_context(role, state, role.value)

    system, _ = LocalModelRuntime(Settings(_env_file=None))._prompts(
        role, envelope, type(candidate), candidate.model_dump(mode="json")
    )

    assert f"ROLE: {role.value}" in system
    assert "RESPONSIBILITY:" in system
    assert "BOUNDARIES:" in system
    assert "EVIDENCE TO PRESERVE:" in system
    assert "OUTPUT CONTRACT:" in system
    assert "NO ROUTING / NO MODEL SELECTION:" in system
