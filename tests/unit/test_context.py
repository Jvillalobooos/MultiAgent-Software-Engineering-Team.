import pytest

from engineering_team.contracts.enums import (
    ActionMode,
    AgentRole,
    ProjectCapabilityStatus,
    ProjectEcosystem,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import (
    ImplementationResult,
    ProjectCapabilityProfile,
    ProjectCommand,
    ReviewerDecision,
    SecurityFinding,
    SecurityReview,
    ToolResult,
)
from engineering_team.contracts.models import (
    TestResult as EngineeringTestResult,
)
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def test_product_context_excludes_repository_and_secrets() -> None:
    state = EngineeringState(run_id="r1", requirement="feature", repository_context={"secret": "x"})
    envelope = build_context(AgentRole.PRODUCT, state, "analyze")

    assert envelope.state_projection == {
        "run_id": "r1",
        "requirement": "feature",
        "project_capabilities": None,
    }


def test_context_rejects_unknown_fields() -> None:
    state = EngineeringState(run_id="r1", requirement="feature")
    with pytest.raises(ValueError):
        build_context(AgentRole.PRODUCT, state, "analyze", extra_projection={"secret": "x"})


@pytest.mark.parametrize("role", list(AgentRole))
def test_every_agent_context_receives_the_validated_project_profile(role: AgentRole) -> None:
    profile = ProjectCapabilityProfile.create(
        status=ProjectCapabilityStatus.SUPPORTED,
        ecosystem=ProjectEcosystem.PYTHON,
        commands={"test": ProjectCommand(argv=["python", "-m", "pytest"])},
        required_capabilities=["test"],
    )
    state = EngineeringState(
        run_id="r1",
        requirement="feature",
        project_capabilities=profile,
    )

    envelope = build_context(role, state, "analyze")

    assert envelope.state_projection["project_capabilities"] == profile


def test_reviewer_context_deduplicates_and_bounds_tool_output() -> None:
    state = EngineeringState(
        run_id="run", requirement="requirement",
        tool_results=[
            ToolResult(
                tool_name="run_tests", allowed_role=AgentRole.TESTING, status=ToolStatus.SUCCESS,
                input_summary="safe", output_summary="first" * 400, duration_ms=1,
            ),
            ToolResult(
                tool_name="run_tests", allowed_role=AgentRole.TESTING, status=ToolStatus.SUCCESS,
                input_summary="safe", output_summary="latest" * 400, duration_ms=1,
            ),
        ],
    )

    envelope = build_context(AgentRole.REVIEWER, state, "review")

    assert len(envelope.tool_results) == 1
    assert len(envelope.tool_results[0].output_summary) == 600


def test_developer_remediation_sees_latest_causal_test_evidence_without_execution_permission() -> None:
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["src/counter.py"],
        diff="--- a/src/counter.py\n+++ b/src/counter.py\n+def increment(): ...\n",
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    causal_tail = "AttributeError: Counter has no initialized value"
    failed_tool = ToolResult(
        tool_name="run_tests",
        allowed_role=AgentRole.TESTING,
        status=ToolStatus.FAIL,
        input_summary="safe",
        output_summary=("collection detail\n" * 200) + causal_tail,
        duration_ms=1,
        evidence_reference="mcp://quality/run_tests",
    )
    failed_result = EngineeringTestResult(
        proposed_tests=["increment behavior"],
        generated_tests=["tests/test_counter.py"],
        executed_tests=["run_tests"],
        actual_results=[failed_tool.output_summary],
        status=ToolStatus.FAIL,
        failures=[failed_tool.output_summary],
        coverage_mapping={"increment": ["tests/test_counter.py"]},
        evidence_references=["mcp://quality/run_tests"],
    )
    review = ReviewerDecision(
        status=ReviewerStatus.REJECTED,
        score=45,
        subscores={},
        problems=["successful workspace test validation is missing"],
        reason="deterministic delivery gate: successful workspace test validation is missing",
        remediation_category=RemediationCategory.IMPLEMENTATION,
        return_to=RouteTarget.DEVELOPER,
        confidence=1,
    )
    state = EngineeringState(
        run_id="causal-remediation",
        requirement="increment a stored counter",
        implementation=implementation,
        test_results=[failed_result],
        review=review,
        tool_results=[failed_tool],
        remediation_request=review.reason,
        iteration=1,
    )

    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)

    assert envelope.remediation_context is not None
    assert envelope.remediation_context.prior_implementation.diff == implementation.diff
    assert envelope.remediation_context.latest_test_result.status is ToolStatus.FAIL
    visible = envelope.remediation_context.causal_tool_results
    assert len(visible) == 1
    assert visible[0].tool_name == "run_tests"
    assert visible[0].status is ToolStatus.FAIL
    assert visible[0].evidence_reference == "mcp://quality/run_tests"
    assert causal_tail in visible[0].output_summary
    assert len(visible[0].output_summary) <= 1_600
    assert "run_tests" not in envelope.allowed_tools
    assert all(item.tool_name != "run_tests" for item in envelope.tool_results)


def test_developer_security_remediation_sees_latest_scanner_cause_without_scanner_permission() -> None:
    finding = SecurityFinding(
        category="input_validation",
        severity=SecuritySeverity.HIGH,
        description="unvalidated flow",
        affected_evidence=["mcp://quality/run_security_scan"],
        recommendation="validate input",
    )
    review = SecurityReview(
        status=SecurityStatus.FAIL,
        highest_severity=SecuritySeverity.HIGH,
        findings=[finding], recommendations=["validate input"],
        sources=["mcp://quality/run_security_scan"],
        checklist={key: ("FAIL" if key == "input_validation" else "PASS") for key in (
            "authentication", "authorization", "input_validation", "sensitive_information",
            "secrets", "injection", "access_control", "idor", "logging", "data_protection",
            "api_abuse", "rate_limiting", "owasp",
        )},
    )
    scanner = ToolResult(
        tool_name="run_security_scan", allowed_role=AgentRole.SECURITY,
        status=ToolStatus.FAIL, input_summary="safe",
        output_summary="scanner cause: unvalidated flow reaches operation",
        duration_ms=1, evidence_reference="mcp://quality/run_security_scan",
    )
    reviewer = ReviewerDecision(
        status=ReviewerStatus.REJECTED, score=20, subscores={},
        problems=["security validation unsuccessful"], reason="security validation unsuccessful",
        remediation_category=RemediationCategory.SECURITY,
        return_to=RouteTarget.DEVELOPER, confidence=1,
    )
    state = EngineeringState(
        run_id="security-remediation", requirement="validate operation",
        security_review=review, review=reviewer, tool_results=[scanner],
        remediation_request="security validation unsuccessful", iteration=1,
    )

    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)

    assert envelope.remediation_context.security_review == review
    assert envelope.remediation_context.latest_test_result is None
    assert envelope.remediation_context.causal_tool_results == [scanner]
    assert "run_security_scan" not in envelope.allowed_tools
    assert envelope.tool_results == []
