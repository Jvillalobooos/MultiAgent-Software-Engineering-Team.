import itertools

from engineering_team.apply_run import _run_graph_with_events
from engineering_team.contracts.enums import RunEventKind
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.event_trace import EventEmittingTrace
from engineering_team.observability.events import ListRunEventSink
from engineering_team.observability.langfuse import TraceSession


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
    # Product..Reviewer (no rejection cycle) plus FinalReport — a real graph
    # node that the fixed denylist-based filter now correctly reports too.
    assert kinds.count(RunEventKind.NODE_STARTED) == 7
    assert kinds.count(RunEventKind.NODE_FINISHED) == 7
    assert kinds.count(RunEventKind.RUN_FINISHED) == 1  # exactly one terminal event, not two
    assert [event.seq for event in sink.events] == list(range(len(sink.events)))


def test_event_sink_defaults_to_a_null_sink_when_not_provided():
    graph = build_engineering_graph()
    # No sink argument at all — must not raise, must behave like today.
    state = _run_graph_with_events(
        graph, {"run_id": "run-2", "requirement": "safe bounded change"},
        run_id="run-2", trace=None,
    )
    assert state["final_status"] == "APPROVED"


def test_event_emitting_trace_and_callback_handler_wired_together_like_run_on_project():
    # run_on_project (apply_run.py) wires EventEmittingTrace (wrapping the
    # real TraceSession) AND RunEventCallbackHandler together, sharing one
    # seq_counter, and passes the EventEmittingTrace as `trace=` into
    # build_engineering_graph AND as `trace=` into _run_graph_with_events.
    # No prior test exercised that combination — which is exactly the
    # configuration that produced two RUN_FINISHED events per run (the
    # graph's FinalReport node calls trace.finish(), and
    # _run_graph_with_events also emits its own RUN_FINISHED afterward).
    sink = ListRunEventSink()
    seq_counter = itertools.count()
    trace_session = TraceSession(trace_id="t1", run_id="run-wired", live=False)
    event_trace = EventEmittingTrace(
        trace=trace_session, sink=sink, run_id="run-wired", seq_counter=seq_counter,
    )
    graph = build_engineering_graph(trace=event_trace)

    state = _run_graph_with_events(
        graph, {"run_id": "run-wired", "requirement": "safe bounded change"},
        run_id="run-wired", trace=event_trace, sink=sink, seq_counter=seq_counter,
    )

    assert state["final_status"] == "APPROVED"
    assert trace_session.finished is True  # the underlying trace was still closed

    kinds = [event.kind for event in sink.events]
    assert kinds.count(RunEventKind.RUN_FINISHED) == 1
    assert kinds[-1] == RunEventKind.RUN_FINISHED

    seqs = [event.seq for event in sink.events]
    assert seqs == list(range(len(sink.events)))  # no seq collisions

    started = [event.agent for event in sink.events if event.kind == RunEventKind.NODE_STARTED]
    finished = [event.agent for event in sink.events if event.kind == RunEventKind.NODE_FINISHED]
    assert sorted(started) == sorted(finished)  # every NODE_STARTED has a matching NODE_FINISHED
