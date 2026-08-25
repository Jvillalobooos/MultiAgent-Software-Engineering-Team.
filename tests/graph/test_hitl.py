import pytest
from langgraph.types import Command

from engineering_team.contracts.enums import AgentRole, SecuritySeverity, SecurityStatus
from engineering_team.contracts.models import SecurityFinding, SecurityReview
from engineering_team.contracts.state import EngineeringState
from engineering_team.graph.hitl import record_human_decision, require_human_review
from engineering_team.graph.stategraph import build_engineering_graph

CHECKLIST = {key: "PASS" for key in (
    "authentication", "authorization", "input_validation", "sensitive_information",
    "secrets", "injection", "access_control", "idor", "logging", "data_protection",
    "api_abuse", "rate_limiting", "owasp",
)}


def test_hitl_pauses_until_valid_explicit_human_decision() -> None:
    paused = require_human_review(EngineeringState(run_id="r", requirement="critical"))

    assert paused.human_review_required is True
    assert paused.final_status == "HUMAN_REVIEW_REQUIRED"
    with pytest.raises(ValueError):
        record_human_decision(paused, "anything")

    resumed = record_human_decision(paused, "RESUME")
    assert resumed.human_decision == "RESUME"
    assert resumed.human_review_required is False
    assert resumed.final_status is None


def test_hitl_human_can_terminate() -> None:
    paused = require_human_review(EngineeringState(run_id="r", requirement="critical"))
    terminated = record_human_decision(paused, "TERMINATE")

    assert terminated.human_decision == "TERMINATE"
    assert terminated.final_status == "HUMAN_REVIEW_REQUIRED"


class CriticalSecurity:
    def execute(self, envelope):
        finding = SecurityFinding(
            category="secrets", severity=SecuritySeverity.CRITICAL,
            description="critical exposure", affected_evidence=["diff"],
            recommendation="contain", sources=[],
        )
        return SecurityReview(
            status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.CRITICAL,
            findings=[finding], recommendations=["contain"], sources=[],
            checklist=CHECKLIST, requires_hitl=True,
        )


def test_langgraph_hitl_is_checkpointed_and_resumable() -> None:
    graph = build_engineering_graph(
        agent_overrides={AgentRole.SECURITY: CriticalSecurity()}, interactive_hitl=True
    )
    config = {"configurable": {"thread_id": "hitl-resume"}}

    paused = graph.invoke({"run_id": "hitl", "requirement": "critical"}, config)
    assert paused["__interrupt__"]

    resumed = graph.invoke(Command(resume="TERMINATE"), config)
    assert resumed["human_decision"] == "TERMINATE"
    assert resumed["final_status"] == "HUMAN_REVIEW_REQUIRED"


def test_langgraph_hitl_resume_continues_predefined_validation_route() -> None:
    graph = build_engineering_graph(
        agent_overrides={AgentRole.SECURITY: CriticalSecurity()}, interactive_hitl=True
    )
    config = {"configurable": {"thread_id": "hitl-continue"}}
    paused = graph.invoke({"run_id": "hitl", "requirement": "critical"}, config)
    assert paused["__interrupt__"]

    continued = graph.invoke(Command(resume="RESUME"), config)

    assert continued["human_decision"] == "RESUME"
    assert "Testing" in continued["route_history"]
    assert "Reviewer" in continued["route_history"]
    assert continued["__interrupt__"]  # Critical evidence pauses again; it never auto-approves.
