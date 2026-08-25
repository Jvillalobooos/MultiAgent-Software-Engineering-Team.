from collections import deque

import httpx
import pytest

from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import (
    AgentRole,
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
