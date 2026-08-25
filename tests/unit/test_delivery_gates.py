from engineering_team.contracts.enums import ActionMode, AgentRole, SecurityStatus, ToolStatus
from engineering_team.contracts.models import ImplementationResult, SecurityReview, ToolResult
from engineering_team.contracts.models import TestResult as Result
from engineering_team.contracts.state import EngineeringState
from engineering_team.graph.stategraph import approval_problems


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
