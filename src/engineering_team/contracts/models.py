import hashlib
import json
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import (
    ActionMode,
    AgentRole,
    DeveloperBlocker,
    ErrorCode,
    ProjectCapabilityStatus,
    ProjectEcosystem,
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


class FileMutation(StrictModel):
    path: str
    operation: Literal["create", "update"]
    content: str = Field(min_length=1)


class ImplementationResult(StrictModel):
    action_mode: ActionMode
    changed_files: list[str]
    diff: str
    evidence: list[str]
    validation_result: str
    security_surface_changed: bool = False
    mutations: list[FileMutation] = Field(default_factory=list)
    blocker: DeveloperBlocker | None = None

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
    test_mutations: list[FileMutation] = Field(default_factory=list)


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


class ProjectCommand(StrictModel):
    argv: list[str] = Field(min_length=1)
    accepts_paths: bool = False
    cwd: str = "."

    @field_validator("argv")
    @classmethod
    def non_empty_argv(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("argv entries must be non-empty")
        return value

    @field_validator("cwd")
    @classmethod
    def safe_relative_cwd(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or ".." in path.parts
            or (path.parts and ":" in path.parts[0])
        ):
            raise ValueError("cwd must be a safe workspace-relative path")
        return path.as_posix()


class ProjectCapabilityProfile(StrictModel):
    status: ProjectCapabilityStatus
    ecosystem: ProjectEcosystem
    project_root: str = "."
    manifests: list[str] = Field(default_factory=list)
    source_suffixes: list[str] = Field(default_factory=list)
    test_path_patterns: list[str] = Field(default_factory=list)
    commands: dict[str, ProjectCommand] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
    fingerprint: str = ""

    @classmethod
    def create(cls, **values: Any) -> Self:
        return cls.model_validate(values)

    def _expected_fingerprint(self) -> str:
        payload = self.model_dump(
            mode="json",
            exclude={"evidence_references", "fingerprint"},
        )
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @model_validator(mode="after")
    def validate_contract_and_fingerprint(self) -> Self:
        allowed = {"test", "build", "lint", "dependency_check", "security_scan"}
        unknown = set(self.commands) - allowed
        if unknown:
            raise ValueError(f"unsupported command capabilities: {sorted(unknown)}")
        missing = [item for item in self.required_capabilities if item not in self.commands]
        if self.status is ProjectCapabilityStatus.SUPPORTED and missing:
            raise ValueError(f"required capability has no command: {', '.join(missing)}")
        if (
            self.status is ProjectCapabilityStatus.SUPPORTED
            and self.ecosystem is ProjectEcosystem.UNKNOWN
        ):
            raise ValueError("supported profile requires a known ecosystem")
        expected = self._expected_fingerprint()
        if self.fingerprint and self.fingerprint != expected:
            raise ValueError("project capability fingerprint mismatch")
        object.__setattr__(self, "fingerprint", expected)
        return self


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
    project_capabilities: dict[str, Any] | None = None
