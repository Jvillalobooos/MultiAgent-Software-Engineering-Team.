from engineering_team.apply_run import _run_graph_with_events
from engineering_team.contracts.enums import RunEventKind
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.events import ListRunEventSink


def test_full_run_emits_run_started_node_events_and_run_finished_in_order():
    sink = ListRunEventSink()
    graph = build_engineering_graph()

    state = _run_graph_with_events(
        graph,
        {"run_id": "run-1", "requirement": "safe bounded change"},
        run_id="run-1", trace=None, sink=sink,
    )

    assert state["final_status"] == "APPROVED"
    kinds = [event.kind for event in sink.events]
    assert kinds[0] == RunEventKind.RUN_STARTED
    assert kinds[-1] == RunEventKind.RUN_FINISHED
    assert kinds.count(RunEventKind.NODE_STARTED) == 6  # Product..Reviewer, no rejection cycle
    assert kinds.count(RunEventKind.NODE_FINISHED) == 6
    assert [event.seq for event in sink.events] == list(range(len(sink.events)))


def test_event_sink_defaults_to_a_null_sink_when_not_provided():
    graph = build_engineering_graph()
    # No sink argument at all — must not raise, must behave like today.
    state = _run_graph_with_events(
        graph, {"run_id": "run-2", "requirement": "safe bounded change"},
        run_id="run-2", trace=None,
    )
    assert state["final_status"] == "APPROVED"
