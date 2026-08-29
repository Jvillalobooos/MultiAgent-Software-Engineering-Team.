from engineering_team.contracts.enums import (
    ErrorCode,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import ReviewerDecision
from engineering_team.guardrails.secrets import redact_secrets
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
            problems = [finding.description for finding in security.findings]
            if any(finding.category == "security tooling" for finding in security.findings):
                latest_scans = {(item.tool_name, item.input_summary): item
                    for item in envelope.tool_results if item.tool_name in {
                        "run_security_scan", "scan_dependencies", "get_security_report"}}
                failures = [item for item in latest_scans.values()
                            if item.status is not ToolStatus.SUCCESS]
                problems.extend(f"{item.tool_name}: {redact_secrets(item.output_summary[-2000:])}"
                                for item in failures[:2])
            return ReviewerDecision(
                status=ReviewerStatus.REJECTED, score=40,
                subscores={item: (0 if item == "security" else 70) for item in _DIMENSIONS},
                problems=problems,
                reason=("unsafe requirement requires human revision" if security.requires_hitl
                        else "security findings require code remediation"),
                remediation_category=RemediationCategory.SECURITY,
                return_to=None if security.requires_hitl else RouteTarget.DEVELOPER, confidence=1,
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
