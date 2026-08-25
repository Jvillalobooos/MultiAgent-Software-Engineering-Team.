from engineering_team.contracts.enums import (
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
)
from engineering_team.contracts.models import ReviewerDecision
from engineering_team.graph.routers import review_route, security_route


def test_rejected_decision_routes_to_remediation_and_increments_cycle() -> None:
    decision = ReviewerDecision(
        status=ReviewerStatus.REJECTED,
        score=40,
        subscores={},
        reason="fix",
        remediation_category=RemediationCategory.IMPLEMENTATION,
        return_to=RouteTarget.DEVELOPER,
        confidence=0.9,
    )
    assert review_route(decision, iteration=0) == "Developer"


def test_third_failed_cycle_requires_human_review() -> None:
    decision = ReviewerDecision(
        status=ReviewerStatus.REJECTED,
        score=40,
        subscores={},
        reason="fix",
        remediation_category=RemediationCategory.IMPLEMENTATION,
        return_to=RouteTarget.DEVELOPER,
        confidence=0.9,
    )
    assert review_route(decision, iteration=3) == "HUMAN_REVIEW_REQUIRED"


def test_critical_security_always_routes_to_hitl() -> None:
    assert security_route(SecuritySeverity.CRITICAL) == "security_hitl"
