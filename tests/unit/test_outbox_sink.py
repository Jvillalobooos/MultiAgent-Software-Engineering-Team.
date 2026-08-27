import json

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.persistence.db import connect
from engineering_team.persistence.outbox_sink import SqliteOutboxEventSink
from engineering_team.persistence.schema import migrate


def _event(run_id: str, seq: int, **overrides) -> RunEvent:
    fields = {
        "event_id": f"e{seq}", "run_id": run_id, "seq": seq, "trace_id": "t1",
        "kind": RunEventKind.NODE_STARTED, "agent": "Product", "iteration": None,
        "status": None, "summary": "Product started", "metrics": {},
    }
    fields.update(overrides)
    return RunEvent(**fields)


def test_emit_writes_one_outbox_row_per_event(tmp_path):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    sink = SqliteOutboxEventSink(db_path)

    sink.emit(_event("run-1", 0))
    sink.emit(_event("run-1", 1, kind=RunEventKind.NODE_FINISHED, summary="Product finished"))

    conn = connect(db_path)
    rows = conn.execute(
        "SELECT run_id, seq, event_json, published FROM event_outbox ORDER BY seq"
    ).fetchall()
    conn.close()

    assert [(row["run_id"], row["seq"], row["published"]) for row in rows] == [
        ("run-1", 0, 0), ("run-1", 1, 0),
    ]
    stored = json.loads(rows[0]["event_json"])
    assert stored["kind"] == "NODE_STARTED"
    assert stored["summary"] == "Product started"


def test_emit_swallows_errors_instead_of_raising(tmp_path):
    db_path = tmp_path / "does-not-exist" / "nested" / "engineering.db"
    # Deliberately do NOT call migrate() — the table doesn't exist yet.
    sink = SqliteOutboxEventSink(db_path)

    sink.emit(_event("run-1", 0))  # must not raise, per RunEventSink's contract
