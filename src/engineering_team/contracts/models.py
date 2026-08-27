from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ActionMode,
    AgentRole,
    ErrorCode,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
    SecurityStatus,
    ToolStatus,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductSpecification(StrictModel):
    objective: str
    actors: list[str]
    business_rules: list[str]
    constraints: list[str]
    acceptance_criteria: list[str]
    nfrs: list[str]
    ambiguities: list[str]
    assumptions: list[str]
    source_requirement: str = ""


class ArchitectureProposal(StrictModel):
    components: list[str]
    apis: list[str]
    data_changes: list[str]
    integrations: list[str]
    dependencies: list[str]
    decisions: list[str]
    risks: list[str]
    impact: str
    evidence_references: list[str] = Field(default_factory=list)


class ImplementationResult(StrictModel):
    action_mode: ActionMode
    changed_files: list[str]
    diff: str
    evidence: list[str]
    validation_result: str
    security_surface_changed: bool = False
    file_contents: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_detailed_proposal_or_justified_noop(self) -> "ImplementationResult":
        if self.changed_files:
            if not self.diff.strip() or not self.evidence or not self.validation_result.strip():
                raise ValueError("implementation proposal requires diff, evidence, and validation")
            return self
        justified = (
            self.diff.startswith("NO-OP:")
            and bool(self.evidence)
            and "no-op" in self.validation_result.lower()
        )
        if not justified:
            raise ValueError("empty implementation requires a specific no-op justification")
        return self


class SecurityFinding(StrictModel):
    category: str
    severity: SecuritySeverity
    description: str
    affected_evidence: list[str]
    recommendation: str
    sources: list[str] = Field(default_factory=list)


class SecurityReview(StrictModel):
    status: SecurityStatus
    highest_severity: SecuritySeverity
    findings: list[SecurityFinding]
    recommendations: list[str]
    sources: list[str]
    checklist: dict[str, str]
    requires_hitl: bool = False

    @field_validator("checklist")
    @classmethod
    def complete_checklist(cls, value: dict[str, str]) -> dict[str, str]:
        expected = {
            "authentication", "authorization", "input_validation",
            "sensitive_information", "secrets", "injection", "access_control",
            "idor", "logging", "data_protection", "api_abuse", "rate_limiting",
            "owasp",
        }
        if set(value) != expected or any(item not in {"PASS", "FAIL"} for item in value.values()):
            raise ValueError("security checklist requires exactly 13 PASS/FAIL categories")
        return value


class TestResult(StrictModel):
    proposed_tests: list[str]
    generated_tests: list[str]
    executed_tests: list[str]
    actual_results: list[str]
    status: ToolStatus
    failures: list[str]
    coverage_mapping: dict[str, list[str]]
    evidence_references: list[str]


class ReviewerDecision(StrictModel):
    status: ReviewerStatus
    score: float = Field(ge=0, le=100)
    subscores: dict[str, float]
    problems: list[str] = Field(default_factory=list)
    reason: str
    remediation_category: RemediationCategory | None = None
    return_to: RouteTarget | None = None
    confidence: float = Field(ge=0, le=1)
    evidence_references: list[str] = Field(default_factory=list)


class RetrievedEvidence(StrictModel):
    source: str
    section: str
    version: str
    chunk_id: str
    fragment: str
    domain: str
    query: str
    score: float | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ToolResult(StrictModel):
    tool_name: str
    allowed_role: AgentRole
    status: ToolStatus
    input_summary: str
    output_summary: str
    duration_ms: int = Field(ge=0)
    evidence_reference: str | None = None
    error: str | None = None


class ModelExecutionInfo(StrictModel):
    agent: AgentRole
    provider: str
    requested_model: str
    actual_model: str | None = None
    model_profile: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    degraded: bool = False
    latency_ms: int = Field(ge=0)
    usage: dict[str, Any] | None = None
    structured_output_success: bool = False
    error: str | None = None
    http_status: int | None = None
    error_category: str | None = None
    retryable: bool | None = None


class CloudFallbackContext(StrictModel):
    agent: AgentRole
    task: str
    relevant_requirement: str
    structured_input: dict[str, Any]
    validation_error: str | None = None
    rag_fragments: list[str] = Field(default_factory=list)
    code_fragments: list[str] = Field(default_factory=list)
    deterministic_evidence: list[str] = Field(default_factory=list)


class WorkflowError(StrictModel):
    code: ErrorCode
    source_stage: str
    retryable: bool
    detail: str
    evidence_reference: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FinalReport(StrictModel):
    feature: str
    status: str
    requirements: str
    architecture: str
    security: str
    testing: str
    implementation: str
    risk: str
    iterations: int = Field(ge=0)
    documentation_used: list[str]
    tools_executed: list[str]
    models_used: list[str]
    errors_degradations: list[str]
    trace_id: str
    next_action: str
