from engineering_team.agents.product import ProductAgent
from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.contracts.enums import AgentRole, ErrorCode, ReviewerStatus
from engineering_team.contracts.models import WorkflowError
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
    assert set(decision.subscores) == {
        "requirements", "architecture", "security", "testing", "implementation", "rag_grounding",
    }
