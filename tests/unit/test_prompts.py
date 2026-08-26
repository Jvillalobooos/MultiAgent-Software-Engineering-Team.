import pytest

from engineering_team.agents.architecture import ArchitectureAgent
from engineering_team.agents.developer import DeveloperAgent
from engineering_team.agents.product import ProductAgent
from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.agents.testing import TestingAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.runtime import LocalModelRuntime
from engineering_team.models.context import build_context

AGENTS = {
    AgentRole.PRODUCT: ProductAgent,
    AgentRole.ARCHITECTURE: ArchitectureAgent,
    AgentRole.DEVELOPER: DeveloperAgent,
    AgentRole.SECURITY: SecurityAgent,
    AgentRole.TESTING: TestingAgent,
    AgentRole.REVIEWER: ReviewerAgent,
}


@pytest.mark.parametrize("role", list(AgentRole))
def test_consumed_system_prompt_declares_role_boundaries_evidence_and_authority(role) -> None:
    state = EngineeringState(run_id="prompt", requirement="safe bounded change")
    envelope = build_context(role, state, role.value)
    candidate = AGENTS[role]().execute(envelope)

    system, _ = LocalModelRuntime(Settings(_env_file=None))._prompts(
        role, envelope, type(candidate), candidate.model_dump(mode="json")
    )

    assert f"ROLE: {role.value}" in system
    assert "RESPONSIBILITY:" in system
    assert "BOUNDARIES:" in system
    assert "EVIDENCE TO PRESERVE:" in system
    assert "OUTPUT CONTRACT:" in system
    assert "NO ROUTING / NO MODEL SELECTION:" in system


def test_developer_prompt_requires_mutations_for_a_viable_inspected_change() -> None:
    state = EngineeringState(run_id="prompt", requirement="change a password safely")
    envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
    candidate = DeveloperAgent().execute(envelope)

    system, _ = LocalModelRuntime(Settings(_env_file=None))._prompts(
        AgentRole.DEVELOPER, envelope, type(candidate), candidate.model_dump(mode="json")
    )

    assert "return one or more mutations" in system
