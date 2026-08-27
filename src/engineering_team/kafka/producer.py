"""Drains event_outbox into Kafka with an idempotent producer.

Every row gets published exactly once (per outbox row) and is marked
`published=1` afterward regardless of whether it went to the real topic or
the DLQ — a row that can't be parsed must not be retried forever.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from confluent_kafka import Producer

from ..persistence.db import connect
from .topics import RUN_DLQ_TOPIC, RUN_EVENTS_TOPIC


class OutboxPublisher:
    def __init__(self, db_path: str | Path, bootstrap_servers: str) -> None:
        self._db_path = Path(db_path)
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "enable.idempotence": True,
            "acks": "all",
        })
        self._stop_event = threading.Event()

    def drain_once(self) -> int:
        conn = connect(self._db_path)
        try:
            rows = conn.execute(
                "SELECT outbox_id, run_id, seq, event_json FROM event_outbox "
                "WHERE published = 0 ORDER BY outbox_id"
            ).fetchall()
            for row in rows:
                topic, value = self._topic_and_value(row["run_id"], row["event_json"])
                self._producer.produce(topic, key=row["run_id"], value=value)
                self._producer.flush(timeout=10.0)
                conn.execute(
                    "UPDATE event_outbox SET published = 1 WHERE outbox_id = ?",
                    (row["outbox_id"],),
                )
                conn.commit()
            return len(rows)
        finally:
            conn.close()

    def _topic_and_value(self, run_id: str, event_json: str) -> tuple[str, bytes]:
        try:
            json.loads(event_json)  # validate it round-trips as JSON
        except (ValueError, TypeError):
            return RUN_DLQ_TOPIC, event_json.encode("utf-8", errors="replace")
        return RUN_EVENTS_TOPIC, event_json.encode("utf-8")

    def run_forever(self, poll_interval_seconds: float = 1.0) -> None:
        while not self._stop_event.is_set():
            self.drain_once()
            self._stop_event.wait(poll_interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
