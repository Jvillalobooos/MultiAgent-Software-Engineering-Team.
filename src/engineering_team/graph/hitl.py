from engineering_team.contracts.state import EngineeringState


def require_human_review(state: EngineeringState) -> EngineeringState:
    return state.model_copy(
        update={"human_review_required": True, "final_status": "HUMAN_REVIEW_REQUIRED"}
    )


def record_human_decision(state: EngineeringState, decision: str) -> EngineeringState:
    """Record only the two predefined HITL outcomes; humans cannot invent routes."""
    normalized = decision.strip().upper()
    if normalized not in {"RESUME", "TERMINATE"}:
        raise ValueError("human decision must be RESUME or TERMINATE")
    if not state.human_review_required:
        raise ValueError("workflow is not paused for human review")
    if normalized == "RESUME":
        return state.model_copy(
            update={
                "human_decision": normalized,
                "human_review_required": False,
                "final_status": None,
            }
        )
    return state.model_copy(update={"human_decision": normalized})
