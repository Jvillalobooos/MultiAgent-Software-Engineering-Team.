"""Drains event_outbox into Kafka with an idempotent producer.

A row is marked `published=1` only once its Kafka delivery report has
actually confirmed success — never on the strength of `produce()` alone,
which only enqueues the message. A delivery failure or a `flush()` timeout
(the delivery report never arrives in time) leaves the row `published=0`,
so the next `drain_once()` call retries it; nothing is marked handled
without a confirmed outcome. This applies equally to the real topic and
the DLQ path — sending to the DLQ is still a real produce that can fail.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Protocol

from confluent_kafka import Producer

from ..persistence.db import connect
from .topics import RUN_DLQ_TOPIC, RUN_EVENTS_TOPIC

_DEFAULT_FLUSH_TIMEOUT_SECONDS = 10.0


class _ProducerLike(Protocol):
    def produce(self, topic: str, *, key: str, value: bytes, on_delivery: Any) -> None: ...
    def flush(self, timeout: float) -> int: ...


class OutboxPublisher:
    def __init__(
        self,
        db_path: str | Path,
        bootstrap_servers: str,
        *,
        producer: _ProducerLike | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._producer: _ProducerLike = producer or Producer({
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
            published_count = 0
            for row in rows:
                topic, value = self._topic_and_value(row["run_id"], row["event_json"])
                if not self._produce_and_confirm(topic, row["run_id"], value):
                    continue  # delivery failed or timed out — stays published=0 for retry
                conn.execute(
                    "UPDATE event_outbox SET published = 1 WHERE outbox_id = ?",
                    (row["outbox_id"],),
                )
                conn.commit()
                published_count += 1
            return published_count
        finally:
            conn.close()

    def _produce_and_confirm(
        self, topic: str, key: str, value: bytes,
        timeout: float = _DEFAULT_FLUSH_TIMEOUT_SECONDS,
    ) -> bool:
        """Produce one message and wait for its delivery report.

        Returns True only if the delivery callback fired with no error.
        A timeout (flush() returns >0, meaning the callback never fired)
        or a delivery error both return False — the caller must not mark
        the row published in either case.
        """
        outcome: dict[str, bool] = {"delivered": False}

        def _on_delivery(err: Any, _msg: Any) -> None:
            outcome["delivered"] = err is None

        self._producer.produce(topic, key=key, value=value, on_delivery=_on_delivery)
        still_pending = self._producer.flush(timeout=timeout)
        if still_pending > 0:
            return False  # timed out waiting for the delivery report
        return outcome["delivered"]

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
