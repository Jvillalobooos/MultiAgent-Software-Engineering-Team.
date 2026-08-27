import pytest
from langgraph.graph import StateGraph
from typing_extensions import TypedDict

from engineering_team.agents.security import SecurityAgent
from engineering_team.contracts.enums import (
    AgentRole,
    RunEventKind,
    SecuritySeverity,
    SecurityStatus,
)
from engineering_team.contracts.models import SecurityFinding, SecurityReview
from engineering_team.graph.stategraph import build_engineering_graph, build_walking_graph
from engineering_team.observability.event_callbacks import RunEventCallbackHandler
from engineering_team.observability.events import ListRunEventSink

CHECKLIST = {key: "PASS" for key in (
    "authentication", "authorization", "input_validation", "sensitive_information",
    "secrets", "injection", "access_control", "idor", "logging", "data_protection",
    "api_abuse", "rate_limiting", "owasp",
)}


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


def test_callback_handler_emits_node_started_and_finished_in_order():
    sink = ListRunEventSink()
    handler = RunEventCallbackHandler(sink=sink, run_id="run-1")
    graph = build_walking_graph()

    graph.invoke({"visited": []}, config={"callbacks": [handler]})

    kinds_and_agents = [(event.kind, event.agent) for event in sink.events]
    assert kinds_and_agents == [
        (RunEventKind.NODE_STARTED, "Product"), (RunEventKind.NODE_FINISHED, "Product"),
        (RunEventKind.NODE_STARTED, "Architecture"), (RunEventKind.NODE_FINISHED, "Architecture"),
        (RunEventKind.NODE_STARTED, "Developer"), (RunEventKind.NODE_FINISHED, "Developer"),
        (RunEventKind.NODE_STARTED, "Security"), (RunEventKind.NODE_FINISHED, "Security"),
        (RunEventKind.NODE_STARTED, "Testing"), (RunEventKind.NODE_FINISHED, "Testing"),
        (RunEventKind.NODE_STARTED, "Reviewer"), (RunEventKind.NODE_FINISHED, "Reviewer"),
    ]
    assert [event.seq for event in sink.events] == list(range(12))


def test_callback_handler_ignores_the_outer_graph_wrapper_node():
    sink = ListRunEventSink()
    handler = RunEventCallbackHandler(sink=sink, run_id="run-1")
    graph = build_walking_graph()

    graph.invoke({"visited": []}, config={"callbacks": [handler]})

    assert all(event.agent != "LangGraph" for event in sink.events)


def test_callback_handler_emits_events_for_terminal_hitl_and_final_report_nodes():
    # build_engineering_graph() has real nodes ("FinalReport",
    # "HUMAN_REVIEW_REQUIRED", "security_hitl") beyond the AgentRole set that
    # the old allowlist-based filter silently dropped. Route a run to
    # security_hitl via a CRITICAL security finding and confirm it now
    # produces NODE_STARTED/NODE_FINISHED, while the outer "LangGraph"
    # wrapper still does not.
    sink = ListRunEventSink()
    handler = RunEventCallbackHandler(sink=sink, run_id="run-1")
    graph = build_engineering_graph(agent_overrides={AgentRole.SECURITY: CriticalSecurity()})

    state = graph.invoke(
        {"run_id": "run-1", "requirement": "change"}, config={"callbacks": [handler]}
    )

    assert state["route_history"][-1] == "security_hitl"
    agents_started = {event.agent for event in sink.events if event.kind == RunEventKind.NODE_STARTED}
    agents_finished = {event.agent for event in sink.events if event.kind == RunEventKind.NODE_FINISHED}
    assert "security_hitl" in agents_started
    assert "security_hitl" in agents_finished
    assert "LangGraph" not in agents_started
    assert "LangGraph" not in agents_finished
    # Every NODE_STARTED has a matching NODE_FINISHED for the same agent.
    assert agents_started == agents_finished


def test_callback_handler_emits_node_finished_with_error_status_on_chain_error():
    sink = ListRunEventSink()
    handler = RunEventCallbackHandler(sink=sink, run_id="run-1")

    class State(TypedDict):
        pass

    def boom(state: State) -> State:
        raise RuntimeError("node exploded")

    graph = StateGraph(State)
    graph.add_node("Boom", boom)
    graph.set_entry_point("Boom")
    graph.set_finish_point("Boom")
    compiled = graph.compile()

    with pytest.raises(RuntimeError, match="node exploded"):
        compiled.invoke({}, config={"callbacks": [handler]})

    kinds_and_agents = [(event.kind, event.agent, event.status) for event in sink.events]
    assert (RunEventKind.NODE_STARTED, "Boom", None) in kinds_and_agents
    assert (RunEventKind.NODE_FINISHED, "Boom", "ERROR") in kinds_and_agents
    assert handler._active == {}
