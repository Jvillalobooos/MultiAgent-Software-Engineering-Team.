from engineering_team.agents.product import ProductAgent
from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.contracts.enums import AgentRole, ErrorCode, ReviewerStatus, ToolStatus
from engineering_team.contracts.models import ToolResult, WorkflowError
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context
import pytest


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
    assert reviewed.requires_hitl is True


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
    assert set(decision.subscores) == {
        "requirements", "architecture", "security", "testing", "implementation", "rag_grounding",
    }


@pytest.mark.parametrize("requirement,category", [
    ("Recuperación de contraseña mediante un token que nunca expire", "sensitive information"),
    ("Recuperación de contraseña mediante un token que nunca\nexpire", "sensitive information"),
    ("Password recovery token that never\nexpires", "sensitive information"),
    ("Usar un token de recuperación sin expiración", "sensitive information"),
    ("Consultar transacciones de cualquier usuario sin requerir sesión", "authorization/IDOR"),
])
def test_security_understands_explicit_unsafe_spanish_requirements(requirement, category):
    state = EngineeringState(run_id="r", requirement=requirement)
    product = ProductAgent().execute(build_context(AgentRole.PRODUCT, state, "analyze"))
    reviewed = SecurityAgent().execute(build_context(
        AgentRole.SECURITY, state.model_copy(update={"specification": product}), "review"))
    assert reviewed.status.value == "FAIL"
    assert reviewed.findings[0].category == category
    decision = ReviewerAgent().execute(build_context(
        AgentRole.REVIEWER, state.model_copy(update={"security_review": reviewed}), "review"))
    assert decision.status is ReviewerStatus.REJECTED
    assert decision.subscores["security"] == 0
    assert decision.return_to is None


def test_security_does_not_flag_authenticated_owner_scoped_spanish_requirement():
    state = EngineeringState(run_id="r", requirement="Consultar transacciones del usuario autenticado con verificación de pertenencia")
    product = ProductAgent().execute(build_context(AgentRole.PRODUCT, state, "analyze"))
    reviewed = SecurityAgent().execute(build_context(
        AgentRole.SECURITY, state.model_copy(update={"specification": product}), "review"))
    assert reviewed.status.value == "PASS"


def test_reviewer_keeps_scanner_diagnostic_for_code_remediation():
    tool = ToolResult(tool_name="run_security_scan", allowed_role=AgentRole.SECURITY,
        status=ToolStatus.FAIL, input_summary="project", duration_ms=1,
        output_summary="S608 Possible SQL injection\n  --> banca/perfil.py:53:13")
    state = EngineeringState(run_id="r", requirement="Update own profile", tool_results=[tool])
    security = SecurityAgent().execute(build_context(AgentRole.SECURITY, state, "scan"))
    state = state.model_copy(update={"security_review": security})
    review = ReviewerAgent().execute(build_context(AgentRole.REVIEWER, state, "review"))
    assert review.status is ReviewerStatus.REJECTED
    assert review.return_to.value == "Developer"
    assert "S608" in "\n".join(review.problems)
    assert "banca/perfil.py:53" in "\n".join(review.problems)


@pytest.mark.parametrize("statuses,scopes,expected", [
    ([ToolStatus.FAIL, ToolStatus.SUCCESS], ["project", "project"], "PASS"),
    ([ToolStatus.SUCCESS, ToolStatus.FAIL], ["project", "project"], "FAIL"),
    ([ToolStatus.FAIL, ToolStatus.SUCCESS], ["file-a", "file-b"], "FAIL"),
])
def test_security_uses_latest_scan_for_each_scope_without_erasing_history(statuses, scopes, expected):
    tools = [ToolResult(tool_name="run_security_scan", allowed_role=AgentRole.SECURITY,
                        status=status, input_summary=scope, output_summary="scanner evidence",
                        duration_ms=1, evidence_reference="mcp://security")
             for status, scope in zip(statuses, scopes)]
    state = EngineeringState(run_id="r", requirement="Update own profile", tool_results=tools)
    envelope = build_context(AgentRole.SECURITY, state, "review")
    reviewed = SecurityAgent().execute(envelope)
    assert reviewed.status.value == expected
    assert envelope.tool_results == tools
    assert reviewed.requires_hitl is False
    if expected == "FAIL":
        decision = ReviewerAgent().execute(build_context(
            AgentRole.REVIEWER, state.model_copy(update={"security_review": reviewed}), "review"))
        assert decision.return_to.value == "Developer"
