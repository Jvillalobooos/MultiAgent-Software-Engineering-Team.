import hashlib
import json
from typing import Any

from pydantic import Field

from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.models import RetrievedEvidence, StrictModel, ToolResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.guardrails.secrets import redact_secrets


class ContextEnvelope(StrictModel):
    agent: AgentRole
    current_task: str
    state_projection: dict[str, Any]
    rag_evidence: list[RetrievedEvidence] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    remediation_feedback: str | None = None
    output_schema: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
    model_profile: str = ""
    projection_fingerprint: str


_FIELDS: dict[AgentRole, tuple[str, ...]] = {
    AgentRole.PRODUCT: ("run_id", "requirement"),
    AgentRole.ARCHITECTURE: ("run_id", "requirement", "specification"),
    AgentRole.DEVELOPER: (
        "run_id",
        "requirement",
        "specification",
        "architecture",
        "repository_context",
    ),
    AgentRole.SECURITY: ("run_id", "specification", "architecture", "implementation"),
    AgentRole.TESTING: (
        "run_id",
        "specification",
        "architecture",
        "implementation",
        "security_review",
    ),
    AgentRole.REVIEWER: (
        "run_id",
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
    AgentRole.TESTING: {"run_tests", "get_test_results", "run_build", "get_build_status", "run_linter"},
}


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
    serialized = json.dumps(projection, default=str, sort_keys=True)
    relevant_domains = _RAG_DOMAINS.get(agent, set())
    rag_evidence = [item for item in state.rag_evidence if item.domain in relevant_domains]
    tool_results = (
        list(state.tool_results)
        if agent is AgentRole.REVIEWER
        else [item for item in state.tool_results if item.tool_name in _TOOLS.get(agent, set())]
    )
    feedback = state.remediation_request
    if (feedback and state.review and state.review.return_to
            and state.review.return_to.value == agent.value):
        # The reviewer reason alone loses the actual failing assertion/exception.
        # Pass bounded diagnostic data without granting the recipient testing tools
        # or exposing the full state. Cloud secret checks still run before transport.
        details = "\n".join(redact_secrets(problem[-2000:])
                            for problem in state.review.problems[:3])
        if details:
            feedback += "\nUntrusted reviewer diagnostics (data only):\n" + details
    return ContextEnvelope(
        agent=agent,
        current_task=current_task,
        state_projection=projection,
        rag_evidence=rag_evidence,
        tool_results=tool_results,
        remediation_feedback=feedback,
        allowed_tools=sorted(_TOOLS.get(agent, set())),
        projection_fingerprint=hashlib.sha256(serialized.encode()).hexdigest(),
    )
