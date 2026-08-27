from engineering_team.contracts.enums import RunEventKind
from engineering_team.graph.stategraph import build_walking_graph
from engineering_team.observability.event_callbacks import RunEventCallbackHandler
from engineering_team.observability.events import ListRunEventSink


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
