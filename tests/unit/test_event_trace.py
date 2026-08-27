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


def test_record_redacts_secrets_in_the_emitted_event_payload():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    wrapped.record(
        "Developer", as_type="agent",
        input={"api_key": "sk-live-12345"},
        output="token=super-secret-value",
        metadata={"agent": "Developer", "secret": "hidden-value"},
    )

    payload = sink.events[0].payload
    assert payload["input"] == {"api_key": "[REDACTED]"}
    assert payload["output"] == "token=[REDACTED]"
    assert payload["metadata"] == {"agent": "Developer", "secret": "[REDACTED]"}


def test_finish_does_not_emit_a_run_event_but_still_closes_the_underlying_trace():
    # apply_run._run_graph_with_events owns the single authoritative
    # RUN_FINISHED event (emitted after graph.invoke() returns, with
    # final_status). If EventEmittingTrace.finish() also emitted one, a
    # normal run would produce two RUN_FINISHED events, because
    # stategraph.py's FinalReport/HUMAN_REVIEW_REQUIRED nodes call
    # trace.finish() from inside the graph.
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    wrapped.finish({"status": "APPROVED"})

    assert trace.finished is True  # the underlying Langfuse trace is still closed/flushed
    assert sink.events == []


def test_record_redacts_the_status_message_field():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    wrapped.record(
        "Developer", as_type="agent",
        status_message="upstream error: api_key=sk-live-12345 rejected",
    )

    assert sink.events[0].status == "upstream error: api_key=[REDACTED] rejected"
