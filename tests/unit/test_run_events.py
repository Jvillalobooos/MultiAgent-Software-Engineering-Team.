import pytest
from pydantic import ValidationError

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.observability.events import ListRunEventSink, NullRunEventSink


def test_run_event_requires_schema_version_one_by_default():
    event = RunEvent(
        event_id="e1", run_id="run-1", seq=0, trace_id="t1",
        kind=RunEventKind.RUN_STARTED, agent=None, iteration=None,
        status=None, summary="run started", metrics={},
    )
    assert event.schema_version == 1
    assert event.payload_ref is None
    assert event.payload is None


def test_run_event_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RunEvent(
            event_id="e1", run_id="run-1", seq=0, trace_id="t1",
            kind=RunEventKind.RUN_STARTED, agent=None, iteration=None,
            status=None, summary="x", metrics={}, unexpected="nope",
        )


def _event(seq: int) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}", run_id="run-1", seq=seq, trace_id="t1",
        kind=RunEventKind.RUN_STARTED, agent=None, iteration=None,
        status=None, summary="x", metrics={},
    )


def test_null_sink_accepts_and_discards_events():
    sink = NullRunEventSink()
    sink.emit(_event(0))  # must not raise


def test_list_sink_preserves_emission_order():
    sink = ListRunEventSink()
    sink.emit(_event(0))
    sink.emit(_event(1))
    assert [event.seq for event in sink.events] == [0, 1]
