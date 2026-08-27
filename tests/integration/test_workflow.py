from collections import deque

import httpx
import pytest

from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import (
    AgentRole,
    ErrorCode,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import (
    ModelExecutionInfo,
    ReviewerDecision,
    SecurityFinding,
    SecurityReview,
    ToolResult,
)
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.llm.cloud import CloudModelRuntime
from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient
from engineering_team.observability.langfuse import LangfuseTracer

CHECKLIST = {key: "PASS" for key in (
    "authentication", "authorization", "input_validation", "sensitive_information",
    "secrets", "injection", "access_control", "idor", "logging", "data_protection",
    "api_abuse", "rate_limiting", "owasp",
)}


def rejected(category, target):
    return ReviewerDecision(
        status=ReviewerStatus.REJECTED, score=40, subscores={}, problems=["fix"],
        reason="fix", remediation_category=category, return_to=target, confidence=0.9,
    )


class ScriptedReviewer(ReviewerAgent):
    def __init__(self, decisions):
        self.decisions = deque(decisions)
        self.calls = 0

    def execute(self, envelope):
        self.calls += 1
        return self.decisions.popleft() if self.decisions else super().execute(envelope)


@pytest.mark.parametrize(
    ("decision", "expected_tail"),
    [
        (rejected(RemediationCategory.ARCHITECTURE, RouteTarget.ARCHITECTURE),
         ["Architecture", "Developer", "Security", "Testing", "Reviewer"]),
        (rejected(RemediationCategory.IMPLEMENTATION, RouteTarget.DEVELOPER),
         ["Developer", "Security", "Testing", "Reviewer"]),
        (rejected(RemediationCategory.SECURITY, RouteTarget.DEVELOPER),
         ["Developer", "Security", "Testing", "Reviewer"]),
        (rejected(RemediationCategory.TESTING, RouteTarget.DEVELOPER),
         ["Developer", "Testing", "Reviewer"]),
    ],
)
def test_reviewer_remediation_chains_return_through_required_validation(decision, expected_tail):
    reviewer = ScriptedReviewer([decision])
    graph = build_engineering_graph(agent_overrides={AgentRole.REVIEWER: reviewer})

    result = graph.invoke({"run_id": "remediation", "requirement": "safe bounded change"})

    first_reviewer = result["route_history"].index("Reviewer")
    assert result["route_history"][first_reviewer + 1 : first_reviewer + 1 + len(expected_tail)] == expected_tail
    assert result["iteration"] == 1
    assert result["final_status"] == "APPROVED"


def test_third_rejected_cycle_stops_without_a_fourth_cycle():
    decision = rejected(RemediationCategory.IMPLEMENTATION, RouteTarget.DEVELOPER)
    reviewer = ScriptedReviewer([decision, decision, decision, decision])
    graph = build_engineering_graph(agent_overrides={AgentRole.REVIEWER: reviewer})

    result = graph.invoke({"run_id": "max", "requirement": "bounded change"})

    assert result["iteration"] == 3
    assert result["human_review_required"] is True
    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert reviewer.calls == 3


class CriticalSecurity(SecurityAgent):
    def execute(self, envelope):
        finding = SecurityFinding(
            category="secrets", severity=SecuritySeverity.CRITICAL,
            description="critical exposure", affected_evidence=["diff"],
            recommendation="human containment", sources=[],
        )
        return SecurityReview(
            status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.CRITICAL,
            findings=[finding], recommendations=[finding.recommendation], sources=[],
            checklist=CHECKLIST,
            requires_hitl=True,
        )


def test_critical_security_routes_to_hitl_before_reviewer():
    reviewer = ScriptedReviewer([])
    graph = build_engineering_graph(
        agent_overrides={AgentRole.SECURITY: CriticalSecurity(), AgentRole.REVIEWER: reviewer}
    )

    result = graph.invoke({"run_id": "critical", "requirement": "change"})

    assert result["route_history"][-1] == "security_hitl"
    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert reviewer.calls == 0


class FailThenPassQuality:
    def __init__(self):
        self.calls = 0

    def run_tests(self, role, paths=None):
        self.calls += 1
        status = ToolStatus.FAIL if self.calls == 1 else ToolStatus.SUCCESS
        return ToolResult(
            tool_name="run_tests", allowed_role=role, status=status, input_summary="safe",
            output_summary="1 failed" if status is ToolStatus.FAIL else "1 passed", duration_ms=1,
        )


def test_failed_mcp_test_result_changes_reviewer_route_and_is_remediated():
    quality = FailThenPassQuality()
    result = build_engineering_graph(quality_mcp=quality).invoke(
        {"run_id": "mcp", "requirement": "safe change"}
    )

    assert result["tool_results"][0].status is ToolStatus.FAIL
    assert result["test_results"][0].status is ToolStatus.FAIL
    assert result["review"].status is ReviewerStatus.APPROVED
    assert result["iteration"] == 1
    assert result["route_history"].count("Reviewer") == 2
    assert result["route_history"][-4:] == ["Developer", "Testing", "Reviewer", "FinalReport"]


def test_real_mcp_protocol_failure_changes_reviewer_route_and_is_remediated(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "test_protocol_route.py").write_text(
        "from pathlib import Path\n"
        "def test_fail_once():\n"
        "    marker = Path('.mcp-remediated')\n"
        "    if not marker.exists():\n"
        "        marker.write_text('remediated', encoding='utf-8')\n"
        "        assert False\n",
        encoding="utf-8",
    )
    trace = LangfuseTracer(offline_directory=tmp_path / "traces").start_run(
        "real-mcp", "safe bounded change"
    )

    with MCPQualityClient(tmp_path) as quality:
        result = build_engineering_graph(quality_mcp=quality, trace=trace).invoke(
            {"run_id": "real-mcp", "requirement": "safe bounded change"}
        )

    failed = [item for item in result["tool_results"] if item.tool_name == "run_tests"]
    assert failed[0].status is ToolStatus.FAIL
    assert result["test_results"][0].status is ToolStatus.FAIL
    first_reviewer = result["route_history"].index("Reviewer")
    assert result["route_history"][first_reviewer + 1 : first_reviewer + 4] == [
        "Developer", "Testing", "Reviewer"
    ]
    assert result["final_status"] == "APPROVED"
    protocol_events = [
        event for event in trace.events
        if event["name"] == "MCP call" and event["metadata"].get("transport") == "stdio"
    ]
    assert protocol_events
    assert all(event["metadata"]["protocol_version"] for event in protocol_events)
    assert any(item.code is ErrorCode.TOOL_ERROR for item in result["errors"])
    assert any(event["name"] == "TOOL_ERROR" for event in trace.events)


def test_required_repository_mcp_unavailable_is_recorded_and_cannot_approve(tmp_path):
    missing_root = tmp_path / "missing-workspace"
    repository = MCPRepositoryClient(missing_root, timeout_seconds=2)
    trace = LangfuseTracer(offline_directory=tmp_path / "traces").start_run(
        "mcp-unavailable", "safe bounded change"
    )

    try:
        result = build_engineering_graph(repository_mcp=repository, trace=trace).invoke(
            {"run_id": "mcp-unavailable", "requirement": "safe bounded change"}
        )
    finally:
        repository.close()

    assert any(item.status is ToolStatus.UNAVAILABLE for item in result["tool_results"])
    assert any(item.code is ErrorCode.MCP_ERROR for item in result["errors"])
    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert result.get("review") is None
    assert any(event["name"] == "MCP_ERROR" for event in trace.events)
    assert not any(item.fallback_used for item in result["model_usage"])


def test_workflow_searches_and_reads_relevant_repository_files_for_developer(tmp_path):
    (tmp_path / "README.md").write_text("general notes\n", encoding="utf-8")
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "misc.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "transactions.py").write_text(
        "def transaction_history(connection, owner_id):\n"
        "    return connection.execute('SELECT * FROM transactions').fetchall()\n",
        encoding="utf-8",
    )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "developer-relevance",
            "requirement": (
                "Return only the latest five transactions belonging to the authorized user."
            ),
        })

    developer_tools = [
        item for item in result["tool_results"]
        if item.allowed_role is AgentRole.DEVELOPER
    ]
    assert "search_code" in [item.tool_name for item in developer_tools]
    assert "read_file" in [item.tool_name for item in developer_tools]
    assert result["implementation"].changed_files == ["app/transactions.py"]
    assert "transaction_history" in result["implementation"].diff


class FailingLocalRuntime:
    def __init__(self):
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate):
        info = ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local", actual_model=None,
            model_profile="LOCAL", degraded=True, latency_ms=1,
            structured_output_success=False, error="LLM_AVAILABILITY_ERROR: unavailable",
        )
        self.attempts.append(info)
        raise RuntimeError(info.error)


class TimingOutLocalRuntime(FailingLocalRuntime):
    def invoke_artifact(self, role, envelope, candidate):
        info = ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local", actual_model=None,
            model_profile="LOCAL", degraded=True, latency_ms=1,
            structured_output_success=False, error="AGENT_TIMEOUT: controlled",
        )
        self.attempts.append(info)
        raise RuntimeError(info.error)


class QualityFailureDuringTestingRuntime:
    """Only the Testing model fails to return its schema-valid artifact."""

    def __init__(self):
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate, *, fallback_reason=None):
        if role is AgentRole.TESTING:
            info = ModelExecutionInfo(
                agent=role, provider="ollama", requested_model="local", actual_model=None,
                model_profile="LOCAL", degraded=True, latency_ms=1,
                structured_output_success=False,
                error="LLM_QUALITY_ERROR: invalid structured response",
            )
            self.attempts.append(info)
            raise RuntimeError(info.error)
        return candidate, ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local", actual_model="local",
            model_profile="LOCAL", latency_ms=1, structured_output_success=True,
        )


class RecordingRuntime:
    def __init__(self):
        self.roles = []
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate):
        self.roles.append(role)
        return candidate, ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local", actual_model="local",
            model_profile="LOCAL", latency_ms=1, structured_output_success=True,
        )


class SuccessfulCloudRuntime:
    def invoke_artifact(self, role, envelope, candidate, *, fallback_reason):
        return candidate, ModelExecutionInfo(
            agent=role, provider="google", requested_model="gemini-3.7-flash",
            actual_model="gemini-3.7-flash", model_profile="CLOUD_FALLBACK",
            fallback_used=True, fallback_reason=fallback_reason, latency_ms=2,
            structured_output_success=True,
        )


def test_local_failure_uses_graph_integrated_cloud_fallback_and_preserves_error():
    result = build_engineering_graph(
        model_runtime=FailingLocalRuntime(), cloud_runtime=SuccessfulCloudRuntime()
    ).invoke({"run_id": "fallback", "requirement": "safe bounded change"})

    assert result["final_status"] == "APPROVED"
    assert result["errors"][0].code.value == "LLM_AVAILABILITY_ERROR"
    assert any(item.fallback_used for item in result["model_usage"])
    assert result["model_usage"][1].fallback_reason == "LLM_AVAILABILITY_ERROR"


def test_local_failure_without_cloud_routes_to_terminal_hitl_instead_of_crashing():
    result = build_engineering_graph(model_runtime=FailingLocalRuntime()).invoke(
        {"run_id": "no-cloud", "requirement": "safe bounded change"}
    )

    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["route_history"] == ["Product", "HUMAN_REVIEW_REQUIRED"]


def test_agent_timeout_is_preserved_in_workflow_and_langfuse():
    trace = LangfuseTracer().start_run("agent-timeout", "safe bounded change")
    result = build_engineering_graph(
        model_runtime=TimingOutLocalRuntime(), trace=trace
    ).invoke({"run_id": "agent-timeout", "requirement": "safe bounded change"})

    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["errors"][0].code is ErrorCode.AGENT_TIMEOUT
    assert result["model_usage"][0].error.startswith("AGENT_TIMEOUT")
    assert any(event["name"] == "AGENT_TIMEOUT" for event in trace.events)


def test_testing_remediation_uses_real_test_failure_without_model_quality_errors():
    quality = FailThenPassQuality()
    result = build_engineering_graph(
        quality_mcp=quality,
        model_runtime=QualityFailureDuringTestingRuntime(),
    ).invoke({"run_id": "testing-quality", "requirement": "safe bounded change"})

    assert result["final_status"] == "APPROVED"
    assert result["iteration"] == 1
    assert result["route_history"][-4:] == ["Developer", "Testing", "Reviewer", "FinalReport"]
    assert not any(item.code is ErrorCode.LLM_QUALITY_ERROR for item in result["errors"])


def test_testing_does_not_fallback_to_a_model_after_cloud_failure():
    quality = FailThenPassQuality()
    local = QualityFailureDuringTestingRuntime()
    result = build_engineering_graph(
        quality_mcp=quality,
        model_runtime=FailingLocalRuntime(),
        cloud_runtime=local,
    ).invoke({"run_id": "cloud-testing-fallback", "requirement": "safe bounded change"})

    assert result["final_status"] == "APPROVED"
    assert local.attempts == []


def test_reviewer_uses_deterministic_evidence_without_an_llm_call():
    runtime = RecordingRuntime()
    result = build_engineering_graph(model_runtime=runtime).invoke(
        {"run_id": "fast-review", "requirement": "safe bounded change"}
    )

    assert result["final_status"] == "APPROVED"
    assert AgentRole.REVIEWER not in runtime.roles


def test_testing_uses_quality_evidence_without_an_llm_call():
    quality = FailThenPassQuality()
    runtime = RecordingRuntime()

    result = build_engineering_graph(
        quality_mcp=quality, model_runtime=runtime
    ).invoke({"run_id": "fast-testing", "requirement": "safe bounded change"})

    assert result["final_status"] == "APPROVED"
    assert result["test_results"][0].status is ToolStatus.FAIL
    assert AgentRole.TESTING not in runtime.roles


def test_failed_cloud_attempt_preserves_budget_model_attempt_and_completed_evidence():
    cloud = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key="configured"),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"error": "rate limited"})
        )),
    )
    result = build_engineering_graph(
        model_runtime=FailingLocalRuntime(), cloud_runtime=cloud,
    ).invoke({"run_id": "cloud-fail", "requirement": "safe bounded change"})

    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["cloud_escalations_run"] == 1
    assert result["cloud_escalations_by_agent"] == {"Product": 1}
    assert result["model_usage"][-1].provider == "google"
    assert result["model_usage"][-1].error.startswith("CLOUD_FALLBACK_UNAVAILABLE")
    assert "rag_evidence" in result and "tool_results" in result
