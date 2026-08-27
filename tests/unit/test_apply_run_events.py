import pytest

from engineering_team.apply_run import _run_graph_with_events
from engineering_team.contracts.enums import RunEventKind
from engineering_team.observability.events import ListRunEventSink


class _ExplodingGraph:
    def invoke(self, initial_state, config=None):
        raise RuntimeError("graph blew up")


def test_run_graph_with_events_emits_run_finished_with_error_status_when_invoke_raises():
    sink = ListRunEventSink()

    with pytest.raises(RuntimeError, match="graph blew up"):
        _run_graph_with_events(
            _ExplodingGraph(), {"run_id": "run-1"},
            run_id="run-1", trace=None, sink=sink,
        )

    kinds = [event.kind for event in sink.events]
    assert kinds == [RunEventKind.RUN_STARTED, RunEventKind.RUN_FINISHED]
    assert sink.events[-1].status == "ERROR"
