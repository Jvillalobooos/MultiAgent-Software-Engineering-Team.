from engineering_team.agents.product import ProductAgent
from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.agents.testing import TestingAgent
from engineering_team.contracts.enums import ActionMode, AgentRole, ErrorCode, ReviewerStatus
from engineering_team.contracts.models import FileMutation, ImplementationResult, WorkflowError
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def test_product_agent_returns_validated_specification() -> None:
    envelope = build_context(
        AgentRole.PRODUCT, EngineeringState(run_id="r", requirement="recover password"), "analyze"
    )
    result = ProductAgent().execute(envelope)

    assert result.objective == "recover password"
    assert result.acceptance_criteria


def test_security_agent_rejects_non_expiring_token_requirement() -> None:
    state = EngineeringState(run_id="r", requirement="non-expiring password reset token")
    product = ProductAgent().execute(build_context(AgentRole.PRODUCT, state, "analyze"))
    reviewed = SecurityAgent().execute(
        build_context(AgentRole.SECURITY, state.model_copy(update={"specification": product}), "review")
    )

    assert reviewed.status.value == "FAIL"
    assert reviewed.findings[0].category == "sensitive information"
    assert len(reviewed.checklist) == 13
    assert reviewed.checklist["sensitive_information"] == "FAIL"


def test_reviewer_rejects_when_required_rag_grounding_failed() -> None:
    state = EngineeringState(
        run_id="r", requirement="grounded design",
        errors=[WorkflowError(
            code=ErrorCode.RAG_ERROR, source_stage="Architecture",
            retryable=False, detail="NO_RELEVANT_DOCS",
        )],
    )
    decision = ReviewerAgent().execute(build_context(AgentRole.REVIEWER, state, "review"))

    assert decision.status is ReviewerStatus.REJECTED
    assert decision.subscores["rag_grounding"] == 0


def test_testing_agent_does_not_hardcode_a_python_test_mutation() -> None:
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["src/service.ts"],
        diff="--- a/src/service.ts\n+++ b/src/service.ts\n+export const value = true;\n",
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    state = EngineeringState(
        run_id="native-testing",
        requirement="change behavior",
        implementation=implementation,
    )

    result = TestingAgent().execute(build_context(AgentRole.TESTING, state, state.requirement))

    assert result.generated_tests == []
    assert result.test_mutations == []


def test_testing_mutation_must_reference_behavior_changed_by_implementation() -> None:
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["app/service.py"],
        diff=(
            "--- a/app/service.py\n+++ b/app/service.py\n"
            "+def change_password(user_id, old_password, new_password):\n"
            "+    return verify_current_password(user_id, old_password)\n"
        ),
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    unrelated = FileMutation(
        path="test_acceptance.py",
        operation="update",
        content="def test_password_recovery():\n    assert True\n",
    )
    grounded = unrelated.model_copy(update={
        "content": (
            "def test_rejects_wrong_current_password(service):\n"
            "    assert service.change_password('u', 'wrong', 'new') is False\n"
        ),
    })

    assert TestingAgent.mutation_is_grounded(implementation, unrelated) is False
    assert TestingAgent.mutation_is_grounded(implementation, grounded) is True


def test_testing_mutation_rejects_source_text_signal_without_behavior_execution() -> None:
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["counter.py"],
        diff="+class Counter:\n+    def increment(self): return 1\n",
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    signal_only = FileMutation(
        path="tests/test_counter.py",
        operation="create",
        content=(
            "from pathlib import Path\n\n"
            "def test_increment_signal_exists():\n"
            "    source = Path('counter.py').read_text(encoding='utf-8')\n"
            "    assert 'increment' in source\n"
        ),
    )

    assert TestingAgent.mutation_is_grounded(implementation, signal_only) is False
