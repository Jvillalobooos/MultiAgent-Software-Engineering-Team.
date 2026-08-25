import pytest
from pydantic import ValidationError

from engineering_team.agents.developer import DeveloperAgent
from engineering_team.contracts.enums import ActionMode, AgentRole, ToolStatus
from engineering_team.contracts.models import (
    ArchitectureProposal,
    ImplementationResult,
    ProductSpecification,
    ToolResult,
)
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def test_developer_proposal_is_detailed_and_grounded_in_inspected_paths() -> None:
    specification = ProductSpecification(
        objective="Add an authorized transaction-history endpoint",
        actors=["User"],
        business_rules=["return at most five owned transactions"],
        constraints=["preserve authorization"],
        acceptance_criteria=["ownership is enforced"],
        nfrs=["secure"],
        ambiguities=[],
        assumptions=[],
        source_requirement="Return five transactions for the authorized user",
    )
    architecture = ArchitectureProposal(
        components=["transaction API"],
        apis=["GET /transactions"],
        data_changes=["owner-scoped query limit"],
        integrations=[],
        dependencies=[],
        decisions=["enforce ownership before limiting to five"],
        risks=["IDOR"],
        impact="bounded API change",
    )
    inspected = ["app/api.py", "app/models.py"]
    state = EngineeringState(
        run_id="developer-proposal",
        requirement=specification.source_requirement,
        specification=specification,
        architecture=architecture,
        tool_results=[ToolResult(
            tool_name="list_files",
            allowed_role=AgentRole.DEVELOPER,
            status=ToolStatus.SUCCESS,
            input_summary="safe",
            output_summary="\n".join(inspected),
            duration_ms=3,
            evidence_reference="mcp://repository/list_files",
        )],
    )

    result = DeveloperAgent().execute(build_context(AgentRole.DEVELOPER, state, "Developer"))

    assert result.changed_files
    assert set(result.changed_files) <= set(inspected)
    assert "GET /transactions" in result.diff
    assert "owner-scoped query limit" in result.diff
    assert result.evidence == ["mcp://repository/list_files"]
    assert "run_build" in result.validation_result
    assert "run_linter" in result.validation_result
    assert "run_tests" in result.validation_result
    assert result.security_surface_changed is True


def test_developer_contract_rejects_unjustified_empty_proposal() -> None:
    with pytest.raises(ValidationError, match="no-op justification"):
        ImplementationResult(
            action_mode=ActionMode.PROPOSED,
            changed_files=[],
            diff="",
            evidence=[],
            validation_result="not applied",
        )
