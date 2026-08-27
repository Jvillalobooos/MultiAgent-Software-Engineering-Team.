"""RunEventSink implementation that durably queues events for Kafka publish.

Writes exactly one row per event into event_outbox, in its own
transaction. Never raises — RunEventSink.emit() must never block or fail
the run it's observing (see observability/events.py's docstring); any
failure here is logged and swallowed, not propagated.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from engineering_team.contracts.models import RunEvent

from .db import connect

logger = logging.getLogger(__name__)


class SqliteOutboxEventSink:
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)

    def emit(self, event: RunEvent) -> None:
        try:
            conn = connect(self._db_path)
            try:
                conn.execute(
                    "INSERT INTO event_outbox (run_id, seq, event_json, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        event.run_id, event.seq,
                        event.model_dump_json(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            logger.exception(
                "SqliteOutboxEventSink failed to persist event run_id=%s seq=%s",
                event.run_id, event.seq,
            )
