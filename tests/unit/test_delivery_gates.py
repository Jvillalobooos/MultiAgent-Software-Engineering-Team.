from engineering_team.contracts.enums import (
    ActionMode,
    AgentRole,
    ProjectCapabilityStatus,
    ProjectEcosystem,
    RemediationCategory,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import (
    ImplementationResult,
    ProjectCapabilityProfile,
    ProjectCommand,
    SecurityReview,
    ToolResult,
)
from engineering_team.contracts.models import TestResult as Result
from engineering_team.contracts.state import EngineeringState
from engineering_team.graph.stategraph import approval_problems, causal_remediation_request


def _write(tool: str, status: ToolStatus = ToolStatus.SUCCESS) -> ToolResult:
    return ToolResult(
        tool_name=tool, allowed_role=AgentRole.DEVELOPER, status=status,
        input_summary="safe", output_summary="app/service.py", duration_ms=1,
        evidence_reference=f"mcp://repository/{tool}",
    )


def test_proposed_implementation_cannot_satisfy_delivery_gate() -> None:
    state = EngineeringState(
        run_id="gate", requirement="add verified email change",
        repository_context={"implementation_required": True},
        implementation=ImplementationResult(
            action_mode=ActionMode.PROPOSED, changed_files=["app/service.py"],
            diff="proposed", evidence=["mcp://repository/read_file"],
            validation_result="proposed validation",
        ),
    )

    assert "implementation is not applied" in approval_problems(state)


def test_write_and_nonempty_diff_satisfy_implementation_evidence_gate() -> None:
    state = EngineeringState(
        run_id="gate", requirement="add verified email change",
        repository_context={"implementation_required": True},
        implementation=ImplementationResult(
            action_mode=ActionMode.APPLIED, changed_files=["app/service.py"],
            diff="--- a/app/service.py\n+++ b/app/service.py\n+verified change\n",
            evidence=["mcp://repository/update_file", "mcp://repository/get_diff"],
            validation_result="write and diff validated",
        ),
        tool_results=[_write("update_file"), _write("get_diff")],
        test_results=[Result(
            proposed_tests=["happy path"], generated_tests=["tests/test_email_change.py"],
            executed_tests=["run_tests"], actual_results=["1 passed"],
            status=ToolStatus.SUCCESS, failures=[], coverage_mapping={}, evidence_references=[],
        )],
    )

    assert approval_problems(state) == []


def test_security_failure_is_a_deterministic_approval_blocker() -> None:
    state = EngineeringState(
        run_id="gate", requirement="add verified email change",
        repository_context={"implementation_required": True},
        implementation=ImplementationResult(
            action_mode=ActionMode.APPLIED, changed_files=["app/service.py"],
            diff="+verified change", evidence=["mcp://repository/get_diff"],
            validation_result="applied",
        ),
        tool_results=[_write("update_file"), _write("get_diff")],
        test_results=[Result(
            proposed_tests=[], generated_tests=["tests/test_change.py"], executed_tests=[],
            actual_results=[], status=ToolStatus.SUCCESS, failures=[], coverage_mapping={},
            evidence_references=[],
        )],
        security_review=SecurityReview(
            status=SecurityStatus.FAIL, highest_severity="HIGH", findings=[], sources=[],
            recommendations=[], requires_hitl=False,
            checklist={
                key: "FAIL" for key in (
                    "authentication", "authorization", "input_validation", "sensitive_information",
                    "secrets", "injection", "access_control", "idor", "logging",
                    "data_protection", "api_abuse", "rate_limiting", "owasp",
                )
            },
        ),
    )

    assert "security review failed" in approval_problems(state)


def test_every_profile_required_capability_needs_successful_tool_evidence() -> None:
    profile = ProjectCapabilityProfile.create(
        status=ProjectCapabilityStatus.SUPPORTED,
        ecosystem=ProjectEcosystem.NODE,
        commands={
            "test": ProjectCommand(argv=["npm", "test"]),
            "build": ProjectCommand(argv=["npm", "run", "build"]),
        },
        required_capabilities=["test", "build"],
    )
    state = EngineeringState(
        run_id="gate",
        requirement="validate project",
        project_capabilities=profile,
        tool_results=[ToolResult(
            tool_name="run_tests", allowed_role=AgentRole.TESTING,
            status=ToolStatus.SUCCESS, input_summary="safe", output_summary="pass",
            duration_ms=1,
        )],
    )

    assert approval_problems(state) == [
        "required project capability 'build' validation is missing or unsuccessful"
    ]

    complete = state.model_copy(update={
        "tool_results": [
            *state.tool_results,
            ToolResult(
                tool_name="run_build", allowed_role=AgentRole.TESTING,
                status=ToolStatus.SUCCESS, input_summary="safe", output_summary="pass",
                duration_ms=1,
            ),
        ],
    })
    assert approval_problems(complete) == []


def test_reviewer_audit_reason_stays_generic_while_remediation_contains_latest_cause() -> None:
    causal = "RuntimeError: counter storage was not initialized"
    failed_tool = ToolResult(
        tool_name="run_tests",
        allowed_role=AgentRole.TESTING,
        status=ToolStatus.FAIL,
        input_summary="safe",
        output_summary=causal,
        duration_ms=1,
        evidence_reference="mcp://quality/run_tests",
    )
    state = EngineeringState(
        run_id="causal-review",
        requirement="increment a stored counter",
        tool_results=[failed_tool],
        test_results=[Result(
            proposed_tests=["behavior"],
            generated_tests=["tests/test_counter.py"],
            executed_tests=["run_tests"],
            actual_results=[causal],
            status=ToolStatus.FAIL,
            failures=[causal],
            coverage_mapping={},
            evidence_references=["mcp://quality/run_tests"],
        )],
    )
    audit_reason = (
        "deterministic delivery gate: successful workspace test validation is missing"
    )

    remediation = causal_remediation_request(state, audit_reason)

    assert audit_reason == (
        "deterministic delivery gate: successful workspace test validation is missing"
    )
    assert "Testing failed. Quality MCP run_tests returned FAIL" in remediation
    assert causal in remediation
    assert "Evidence: mcp://quality/run_tests" in remediation
    assert len(remediation) <= 2_000


def test_security_remediation_selects_latest_scanner_cause_over_stale_test_failure() -> None:
    stale_test = ToolResult(
        tool_name="run_tests", allowed_role=AgentRole.TESTING,
        status=ToolStatus.FAIL, input_summary="safe",
        output_summary="stale test failure", duration_ms=1,
        evidence_reference="mcp://quality/run_tests",
    )
    scanner = ToolResult(
        tool_name="run_security_scan", allowed_role=AgentRole.SECURITY,
        status=ToolStatus.FAIL, input_summary="safe",
        output_summary="current scanner cause", duration_ms=1,
        evidence_reference="mcp://quality/run_security_scan",
    )
    state = EngineeringState(
        run_id="security-cause", requirement="secure operation",
        tool_results=[stale_test, scanner],
        test_results=[Result(
            proposed_tests=[], generated_tests=["tests/test_operation.py"],
            executed_tests=["run_tests"], actual_results=["stale test failure"],
            status=ToolStatus.FAIL, failures=["stale test failure"],
            coverage_mapping={}, evidence_references=["mcp://quality/run_tests"],
        )],
        security_review=SecurityReview(
            status=SecurityStatus.FAIL, highest_severity="HIGH", findings=[],
            recommendations=[], sources=["mcp://quality/run_security_scan"],
            checklist={key: ("FAIL" if key == "input_validation" else "PASS") for key in (
                "authentication", "authorization", "input_validation",
                "sensitive_information", "secrets", "injection", "access_control",
                "idor", "logging", "data_protection", "api_abuse", "rate_limiting",
                "owasp",
            )},
        ),
    )

    remediation = causal_remediation_request(
        state, "security validation unsuccessful", RemediationCategory.SECURITY
    )

    assert "Security failed. Quality MCP run_security_scan returned FAIL" in remediation
    assert "current scanner cause" in remediation
    assert "stale test failure" not in remediation


def test_generic_pregate_remediation_merges_every_currently_active_cause() -> None:
    test_cause = "assert False is True"
    security_cause = "unvalidated flow into sink"
    failed_test = ToolResult(
        tool_name="run_tests", allowed_role=AgentRole.TESTING,
        status=ToolStatus.FAIL, input_summary="safe",
        output_summary=test_cause, duration_ms=1,
        evidence_reference="mcp://quality/run_tests",
    )
    failed_scan = ToolResult(
        tool_name="run_security_scan", allowed_role=AgentRole.SECURITY,
        status=ToolStatus.FAIL, input_summary="safe",
        output_summary=security_cause, duration_ms=1,
        evidence_reference="mcp://quality/run_security_scan",
    )
    state = EngineeringState(
        run_id="merged-cause", requirement="change a password only after confirmation",
        tool_results=[failed_test, failed_scan],
        test_results=[Result(
            proposed_tests=[], generated_tests=["tests/test_password.py"],
            executed_tests=["run_tests"], actual_results=[test_cause],
            status=ToolStatus.FAIL, failures=[test_cause],
            coverage_mapping={}, evidence_references=["mcp://quality/run_tests"],
        )],
        security_review=SecurityReview(
            status=SecurityStatus.FAIL, highest_severity="HIGH", findings=[],
            recommendations=[], sources=["mcp://quality/run_security_scan"],
            checklist={key: ("FAIL" if key == "input_validation" else "PASS") for key in (
                "authentication", "authorization", "input_validation",
                "sensitive_information", "secrets", "injection", "access_control",
                "idor", "logging", "data_protection", "api_abuse", "rate_limiting",
                "owasp",
            )},
        ),
    )
    # No explicit category (or RemediationCategory.IMPLEMENTATION) is what the
    # deterministic pre-gate uses; both active blockers must reach Developer.
    audit_reason = "deterministic delivery gate: multiple gaps"

    remediation = causal_remediation_request(
        state, audit_reason, RemediationCategory.IMPLEMENTATION
    )

    assert "Security failed. Quality MCP run_security_scan returned FAIL" in remediation
    assert security_cause in remediation
    assert "Testing failed. Quality MCP run_tests returned FAIL" in remediation
    assert test_cause in remediation
    assert len(remediation) <= 2_000
