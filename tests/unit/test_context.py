import pytest

from engineering_team.contracts.enums import AgentRole, ReviewerStatus, RouteTarget
from engineering_team.contracts.models import ReviewerDecision
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


def test_remediation_receives_bounded_failure_details_without_testing_tool_access():
    state = EngineeringState(run_id="r1", requirement="recovery",
        remediation_request="failed tests require implementation remediation",
        review=ReviewerDecision(status=ReviewerStatus.REJECTED, score=40,
            subscores={"testing": 0},
            reason="failed tests require implementation remediation", confidence=1,
            return_to=RouteTarget.DEVELOPER,
            problems=["large log " * 1500 + "\nTypeError: can't compare offset-naive and offset-aware datetimes\nbanca/auth.py:94"]))
    developer = build_context(AgentRole.DEVELOPER, state, "fix")
    assert "TypeError" in developer.remediation_feedback
    assert "banca/auth.py:94" in developer.remediation_feedback
    assert len(developer.remediation_feedback) < 6500
    assert "run_tests" not in developer.allowed_tools
    product = build_context(AgentRole.PRODUCT, state, "analyze")
    assert "TypeError" not in product.remediation_feedback
