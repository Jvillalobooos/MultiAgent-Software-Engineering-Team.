from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import Field

from .models import (
    ArchitectureProposal,
    FinalReport,
    ImplementationResult,
    ModelExecutionInfo,
    ProductSpecification,
    RetrievedEvidence,
    ReviewerDecision,
    SecurityReview,
    StrictModel,
    TestResult,
    ToolResult,
    WorkflowError,
)

T = TypeVar("T")


def append_items(current: Sequence[T], incoming: Sequence[T]) -> list[T]:
    """Pure reducer used for append-only evidence collections."""
    return [*current, *incoming]


class EngineeringState(StrictModel):
    run_id: str
    requirement: str
    specification: ProductSpecification | None = None
    repository_context: dict[str, Any] = Field(default_factory=dict)
    architecture: ArchitectureProposal | None = None
    implementation: ImplementationResult | None = None
    security_review: SecurityReview | None = None
    test_results: list[TestResult] = Field(default_factory=list)
    review: ReviewerDecision | None = None
    rag_evidence: list[RetrievedEvidence] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    model_usage: list[ModelExecutionInfo] = Field(default_factory=list)
    iteration: int = Field(default=0, ge=0)
    errors: list[WorkflowError] = Field(default_factory=list)
    human_review_required: bool = False
    final_status: str | None = None
    remediation_request: str | None = None
    next_validation_path: str | None = None
    cloud_escalations_by_agent: dict[str, int] = Field(default_factory=dict)
    cloud_escalations_run: int = Field(default=0, ge=0)
    local_retries_by_stage: dict[str, int] = Field(default_factory=dict)
    local_repairs_by_stage: dict[str, int] = Field(default_factory=dict)
    trace_id: str | None = None
    route_history: list[str] = Field(default_factory=list)
    final_report: FinalReport | None = None
    human_decision: str | None = None
