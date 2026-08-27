from engineering_team.contracts.enums import RunEventKind
from engineering_team.observability.event_trace import EventEmittingTrace
from engineering_team.observability.events import ListRunEventSink
from engineering_team.observability.langfuse import TraceSession


def test_record_forwards_to_the_wrapped_trace_and_emits_an_event():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    observation_id = wrapped.record(
        "Security", as_type="agent", output={"status": "PASS"},
        metadata={"agent": "Security", "iteration": 1},
    )

    assert observation_id == "local-1"
    assert trace.events[0]["name"] == "Security"  # the wrapped TraceSession really recorded it
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.kind == RunEventKind.AGENT
    assert event.agent == "Security"
    assert event.iteration == 1
    assert event.summary == "Security"
    assert event.payload == {"input": None, "output": {"status": "PASS"}, "metadata": {"agent": "Security", "iteration": 1}}


def test_trace_id_and_live_are_passed_through():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=True)
    wrapped = EventEmittingTrace(trace=trace, sink=ListRunEventSink(), run_id="run-1")

    assert wrapped.trace_id == "t1"
    assert wrapped.live is True


def test_finish_emits_a_run_finished_event():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    wrapped.finish({"status": "APPROVED"})

    assert trace.finished is True
    assert sink.events[-1].kind == RunEventKind.RUN_FINISHED
