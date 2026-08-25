import pytest

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ToolResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def test_product_context_excludes_repository_and_secrets() -> None:
    state = EngineeringState(run_id="r1", requirement="feature", repository_context={"secret": "x"})
    envelope = build_context(AgentRole.PRODUCT, state, "analyze")

    assert envelope.state_projection == {"run_id": "r1", "requirement": "feature"}


def test_context_rejects_unknown_fields() -> None:
    state = EngineeringState(run_id="r1", requirement="feature")
    with pytest.raises(ValueError):
        build_context(AgentRole.PRODUCT, state, "analyze", extra_projection={"secret": "x"})


def test_reviewer_context_deduplicates_and_bounds_tool_output() -> None:
    state = EngineeringState(
        run_id="run", requirement="requirement",
        tool_results=[
            ToolResult(
                tool_name="run_tests", allowed_role=AgentRole.TESTING, status=ToolStatus.SUCCESS,
                input_summary="safe", output_summary="first" * 400, duration_ms=1,
            ),
            ToolResult(
                tool_name="run_tests", allowed_role=AgentRole.TESTING, status=ToolStatus.SUCCESS,
                input_summary="safe", output_summary="latest" * 400, duration_ms=1,
            ),
        ],
    )

    envelope = build_context(AgentRole.REVIEWER, state, "review")

    assert len(envelope.tool_results) == 1
    assert len(envelope.tool_results[0].output_summary) == 600
