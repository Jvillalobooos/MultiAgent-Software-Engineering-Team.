import pytest
from pydantic import ValidationError

from engineering_team.contracts.enums import AgentRole, ErrorCode, ReviewerStatus, SecuritySeverity
from engineering_team.contracts.models import FinalReport, ProductSpecification, ReviewerDecision


def test_product_specification_requires_all_governance_fields() -> None:
    with pytest.raises(ValidationError):
        ProductSpecification(objective="only objective")


def test_reviewer_decision_rejects_unapproved_status() -> None:
    with pytest.raises(ValidationError):
        ReviewerDecision(status="MAYBE", score=1, subscores={}, reason="x", confidence=0.1)


def test_final_report_requires_all_contract_fields() -> None:
    with pytest.raises(ValidationError):
        FinalReport(feature="feature")


def test_mandated_enums_are_strict() -> None:
    assert AgentRole.SECURITY.value == "Security"
    assert SecuritySeverity.CRITICAL.value == "CRITICAL"
    assert ReviewerStatus.APPROVED.value == "APPROVED"
    assert ErrorCode.LLM_QUALITY_ERROR.value == "LLM_QUALITY_ERROR"
