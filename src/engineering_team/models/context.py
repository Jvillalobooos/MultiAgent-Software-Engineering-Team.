import hashlib
import json
from typing import Any

from pydantic import Field

from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.models import (
    ImplementationResult,
    RetrievedEvidence,
    SecurityReview,
    StrictModel,
    TestResult,
    ToolResult,
)
from engineering_team.contracts.state import EngineeringState

REMEDIATION_OUTPUT_CHARS = 1_600


class RemediationContext(StrictModel):
    """Bounded causal evidence visible to Developer, never executable authority."""

    reviewer_reason: str
    prior_implementation: ImplementationResult | None = None
    latest_test_result: TestResult | None = None
    security_review: SecurityReview | None = None
    causal_tool_results: list[ToolResult] = Field(default_factory=list, max_length=1)


class ContextEnvelope(StrictModel):
    agent: AgentRole
    current_task: str
    state_projection: dict[str, Any]
    rag_evidence: list[RetrievedEvidence] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    remediation_feedback: str | None = None
    remediation_context: RemediationContext | None = None
    output_schema: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    model_profile: str = ""
    projection_fingerprint: str


_FIELDS: dict[AgentRole, tuple[str, ...]] = {
    AgentRole.PRODUCT: ("run_id", "requirement", "project_capabilities"),
    AgentRole.ARCHITECTURE: (
        "run_id",
        "requirement",
        "project_capabilities",
        "specification",
    ),
    AgentRole.DEVELOPER: (
        "run_id",
        "requirement",
        "project_capabilities",
        "specification",
        "architecture",
        "repository_context",
    ),
    AgentRole.SECURITY: (
        "run_id",
        "project_capabilities",
        "specification",
        "architecture",
        "implementation",
    ),
    AgentRole.TESTING: (
        "run_id",
        "project_capabilities",
        "specification",
        "architecture",
        "implementation",
        "security_review",
    ),
    AgentRole.REVIEWER: (
        "run_id",
        "project_capabilities",
        "specification",
        "architecture",
        "implementation",
        "security_review",
        "test_results",
        "model_usage",
        "errors",
        "iteration",
    ),
}

_RAG_DOMAINS: dict[AgentRole, set[str]] = {
    AgentRole.ARCHITECTURE: {"architecture", "api"},
    AgentRole.DEVELOPER: {"coding"},
    AgentRole.SECURITY: {"security", "owasp"},
    AgentRole.TESTING: {"testing", "coding"},
    AgentRole.REVIEWER: {"architecture", "api", "coding", "security", "owasp", "testing"},
}

_TOOLS: dict[AgentRole, set[str]] = {
    AgentRole.ARCHITECTURE: {"list_files", "read_file", "search_code", "get_file_content"},
    AgentRole.DEVELOPER: {"list_files", "read_file", "search_code", "get_file_content", "create_file", "update_file", "get_diff", "run_build", "get_build_status", "run_linter"},
    AgentRole.SECURITY: {"scan_dependencies", "run_security_scan", "get_security_report"},
    AgentRole.TESTING: {"read_test_file", "create_file", "update_file", "run_tests", "get_test_results", "run_build", "get_build_status", "run_linter"},
}


def bounded_remediation_output(value: str, limit: int = REMEDIATION_OUTPUT_CHARS) -> str:
    if len(value) <= limit:
        return value
    half = (limit - len("\n... bounded ...\n")) // 2
    return f"{value[:half]}\n... bounded ...\n{value[-half:]}"


def _remediation_context(state: EngineeringState) -> RemediationContext | None:
    if not state.remediation_request:
        return None
    latest_test = state.test_results[-1] if state.test_results else None
    bounded_test = None
    if latest_test is not None:
        bounded_test = latest_test.model_copy(update={
            "actual_results": [
                bounded_remediation_output(latest_test.actual_results[-1])
            ] if latest_test.actual_results else [],
            "failures": [
                bounded_remediation_output(latest_test.failures[-1])
            ] if latest_test.failures else [],
        })
    review_category = getattr(state.review, "remediation_category", None)
    security_remediation = getattr(review_category, "value", None) == "SECURITY"
    relevant_names = (
        {"scan_dependencies", "run_security_scan"}
        if security_remediation
        else {"run_tests"}
    )
    causal = next(
        (
            item.model_copy(update={
                "output_summary": bounded_remediation_output(item.output_summary)
            })
            for item in reversed(state.tool_results)
            if item.tool_name in relevant_names and item.status.value != "SUCCESS"
        ),
        None,
    )
    prior = state.implementation
    if prior is not None:
        prior = prior.model_copy(update={
            "diff": bounded_remediation_output(prior.diff, 2_000)
        })
    return RemediationContext(
        reviewer_reason=state.remediation_request,
        prior_implementation=prior,
        latest_test_result=bounded_test if not security_remediation else None,
        security_review=state.security_review if security_remediation else None,
        causal_tool_results=[causal] if causal is not None else [],
    )


def build_context(
    agent: AgentRole,
    state: EngineeringState,
    current_task: str,
    *,
    extra_projection: dict[str, Any] | None = None,
) -> ContextEnvelope:
    if extra_projection:
        raise ValueError("extra projection fields are prohibited")
    projection = {field: getattr(state, field) for field in _FIELDS[agent]}
    remediation_context = (
        _remediation_context(state) if agent is AgentRole.DEVELOPER else None
    )
    serialized = json.dumps(
        {
            "projection": projection,
            "remediation_context": (
                remediation_context.model_dump(mode="json")
                if remediation_context is not None
                else None
            ),
        },
        default=str,
        sort_keys=True,
    )
    relevant_domains = _RAG_DOMAINS.get(agent, set())
    rag_evidence = [item for item in state.rag_evidence if item.domain in relevant_domains]
    if agent is AgentRole.REVIEWER:
        latest_by_tool: dict[str, ToolResult] = {}
        for item in state.tool_results:
            latest_by_tool[item.tool_name] = item
        tool_results = [
            item.model_copy(update={"output_summary": item.output_summary[:600]})
            for item in latest_by_tool.values()
        ]
    else:
        tool_results = [item for item in state.tool_results if item.tool_name in _TOOLS.get(agent, set())]
    return ContextEnvelope(
        agent=agent,
        current_task=current_task,
        state_projection=projection,
        rag_evidence=rag_evidence,
        tool_results=tool_results,
        remediation_feedback=state.remediation_request,
        remediation_context=remediation_context,
        allowed_tools=sorted(_TOOLS.get(agent, set())),
        projection_fingerprint=hashlib.sha256(serialized.encode()).hexdigest(),
    )
