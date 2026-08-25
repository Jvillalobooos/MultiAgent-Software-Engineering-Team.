"""Pure deterministic graph routing functions."""

from engineering_team.contracts.enums import (
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
)
from engineering_team.contracts.models import ReviewerDecision

_ALLOWED_REJECTED_TARGETS = {RouteTarget.ARCHITECTURE, RouteTarget.DEVELOPER}


def review_route(decision: ReviewerDecision, iteration: int) -> str:
    if decision.status is ReviewerStatus.APPROVED:
        return "FinalReport"
    if iteration >= 3:
        return "HUMAN_REVIEW_REQUIRED"
    if decision.return_to not in _ALLOWED_REJECTED_TARGETS:
        return "HUMAN_REVIEW_REQUIRED"
    expected = (
        RouteTarget.ARCHITECTURE
        if decision.remediation_category is RemediationCategory.ARCHITECTURE
        else RouteTarget.DEVELOPER
    )
    if decision.remediation_category is None or decision.return_to is not expected:
        return "HUMAN_REVIEW_REQUIRED"
    return decision.return_to.value


def security_route(severity: SecuritySeverity) -> str:
    return "security_hitl" if severity is SecuritySeverity.CRITICAL else "Testing"
