import pytest
from pydantic import ValidationError

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent


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
