from engineering_team.contracts.enums import (
    ErrorCode,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import ReviewerDecision
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase

_DIMENSIONS = (
    "requirements", "architecture", "security", "testing", "implementation", "rag_grounding",
)


class ReviewerAgent(AgentBase[ReviewerDecision]):
    role = "Reviewer"

    def execute(self, envelope: ContextEnvelope) -> ReviewerDecision:
        projection = envelope.state_projection
        security = projection.get("security_review")
        tests = projection.get("test_results") or []
        latest_test = tests[-1] if tests else None
        evidence = [item.chunk_id for item in envelope.rag_evidence]
        evidence.extend(item.evidence_reference or item.tool_name for item in envelope.tool_results)
        errors = projection.get("errors") or []
        if any(item.code is ErrorCode.RAG_ERROR for item in errors):
            return ReviewerDecision(
                status=ReviewerStatus.REJECTED, score=35,
                subscores={item: (0 if item == "rag_grounding" else 70) for item in _DIMENSIONS},
                problems=["required specialized RAG grounding is unavailable"],
                reason="RAG_ERROR requires architecture remediation or human evidence",
                remediation_category=RemediationCategory.ARCHITECTURE,
                return_to=RouteTarget.ARCHITECTURE, confidence=1,
                evidence_references=evidence,
            )
        if security is not None and security.status is SecurityStatus.FAIL:
            return ReviewerDecision(
                status=ReviewerStatus.REJECTED, score=40,
                subscores={item: (0 if item == "security" else 70) for item in _DIMENSIONS},
                problems=[finding.description for finding in security.findings],
                reason="security findings require code remediation",
                remediation_category=RemediationCategory.SECURITY,
                return_to=RouteTarget.DEVELOPER, confidence=1,
                evidence_references=evidence,
            )
        if latest_test is not None and latest_test.status is not ToolStatus.SUCCESS:
            return ReviewerDecision(
                status=ReviewerStatus.REJECTED, score=45,
                subscores={item: (0 if item == "testing" else 75) for item in _DIMENSIONS},
                problems=list(latest_test.failures), reason="failed tests require implementation remediation",
                remediation_category=RemediationCategory.TESTING,
                return_to=RouteTarget.DEVELOPER, confidence=1,
                evidence_references=evidence,
            )
        return ReviewerDecision(
            status=ReviewerStatus.APPROVED, score=100,
            subscores={item: 100 for item in _DIMENSIONS}, reason="validated evidence satisfies acceptance checks",
            confidence=1, evidence_references=evidence,
        )
