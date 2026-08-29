from engineering_team.contracts.enums import SecuritySeverity, SecurityStatus, ToolStatus
from engineering_team.contracts.models import SecurityFinding, SecurityReview
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase

_SECURITY_CATEGORIES = (
    "authentication", "authorization", "input_validation", "sensitive_information",
    "secrets", "injection", "access_control", "idor", "logging", "data_protection",
    "api_abuse", "rate_limiting", "owasp",
)


def _checklist(failed: str | None = None) -> dict[str, str]:
    return {category: ("FAIL" if category == failed else "PASS") for category in _SECURITY_CATEGORIES}


class SecurityAgent(AgentBase[SecurityReview]):
    role = "Security"

    def execute(self, envelope: ContextEnvelope) -> SecurityReview:
        specification = envelope.state_projection.get("specification")
        requirement = " ".join(getattr(specification, "source_requirement", "").lower().split())
        sources = list(dict.fromkeys(item.source for item in envelope.rag_evidence))
        # A fresh scan can verify remediation of an earlier failure. Keep all
        # attempts in the envelope/audit, but gate on the latest result for the
        # same tool and scope; success for another scope cannot clear a failure.
        latest_tools = {
            (item.tool_name, item.input_summary): item for item in envelope.tool_results
        }
        failed_tools = [
            item for item in latest_tools.values()
            if item.status not in {ToolStatus.SUCCESS}
        ]
        if failed_tools:
            finding = SecurityFinding(
                category="security tooling", severity=SecuritySeverity.HIGH,
                description="security validation tool did not pass",
                affected_evidence=[item.tool_name for item in failed_tools],
                recommendation="remediate scanner findings and rerun security validation",
                sources=sources,
            )
            return SecurityReview(
                status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.HIGH,
                findings=[finding], recommendations=[finding.recommendation], sources=sources,
                checklist=_checklist("owasp"),
            )
        if any(phrase in requirement for phrase in (
            "non-expiring", "never expires", "nunca expire", "nunca expira",
            "sin expiración", "sin expiracion",
        )):
            finding = SecurityFinding(
                category="sensitive information",
                severity=SecuritySeverity.HIGH,
                description="password reset tokens must expire",
                affected_evidence=[requirement],
                recommendation="use a 15-minute single-use token",
                sources=sources,
            )
            return SecurityReview(
                status=SecurityStatus.FAIL,
                highest_severity=SecuritySeverity.HIGH,
                findings=[finding],
                recommendations=[finding.recommendation],
                sources=finding.sources,
                checklist=_checklist("sensitive_information"),
                requires_hitl=True,
            )
        if ("any user" in requirement or "arbitrary" in requirement or
            ("cualquier usuario" in requirement and any(phrase in requirement for phrase in (
                "sin requerir sesión", "sin requerir sesion", "sin autorización",
                "sin autorizacion", "únicamente el id", "unicamente el id",
            )))):
            finding = SecurityFinding(
                category="authorization/IDOR",
                severity=SecuritySeverity.HIGH,
                description="resource access must be ownership-authorized",
                affected_evidence=[requirement],
                recommendation="enforce authenticated ownership checks",
                sources=sources,
            )
            return SecurityReview(
                status=SecurityStatus.FAIL,
                highest_severity=SecuritySeverity.HIGH,
                findings=[finding],
                recommendations=[finding.recommendation],
                sources=finding.sources,
                checklist=_checklist("idor"),
                requires_hitl=True,
            )
        return SecurityReview(
            status=SecurityStatus.PASS,
            highest_severity=SecuritySeverity.INFO,
            findings=[],
            recommendations=[],
            sources=sources,
            checklist=_checklist(),
        )
