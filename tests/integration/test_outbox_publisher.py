import json

from confluent_kafka import Consumer

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.kafka.producer import OutboxPublisher
from engineering_team.kafka.topics import RUN_DLQ_TOPIC, RUN_EVENTS_TOPIC
from engineering_team.persistence.db import connect
from engineering_team.persistence.outbox_sink import SqliteOutboxEventSink
from engineering_team.persistence.schema import migrate


def _event(run_id: str, seq: int) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}", run_id=run_id, seq=seq, trace_id="t1",
        kind=RunEventKind.NODE_STARTED, agent="Product", iteration=None,
        status=None, summary="Product started", metrics={},
    )


def _consume_one(bootstrap_servers: str, topic: str, timeout: float = 10.0):
    consumer = Consumer({
        "bootstrap.servers": bootstrap_servers,
        "group.id": f"test-consumer-{topic}",
        "auto.offset.reset": "earliest",
    })
    consumer.subscribe([topic])
    try:
        msg = consumer.poll(timeout)
        assert msg is not None, f"no message received on {topic} within {timeout}s"
        assert msg.error() is None, msg.error()
        return msg
    finally:
        consumer.close()


def test_drain_once_publishes_outbox_rows_to_run_events_topic(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    sink = SqliteOutboxEventSink(db_path)
    sink.emit(_event("run-pub-1", 0))

    publisher = OutboxPublisher(db_path, kafka_broker)
    published_count = publisher.drain_once()

    assert published_count == 1
    msg = _consume_one(kafka_broker, RUN_EVENTS_TOPIC)
    assert msg.key().decode() == "run-pub-1"
    payload = json.loads(msg.value())
    assert payload["seq"] == 0

    conn = connect(db_path)
    row = conn.execute(
        "SELECT published FROM event_outbox WHERE run_id='run-pub-1' AND seq=0"
    ).fetchone()
    conn.close()
    assert row["published"] == 1


def test_drain_once_sends_unparseable_rows_to_dlq(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO event_outbox (run_id, seq, event_json, created_at) "
        "VALUES ('run-bad', 0, 'not valid json {{{', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()

    publisher = OutboxPublisher(db_path, kafka_broker)
    published_count = publisher.drain_once()

    assert published_count == 1  # counts DLQ deliveries too — the row was handled
    msg = _consume_one(kafka_broker, RUN_DLQ_TOPIC)
    assert msg.key().decode() == "run-bad"

    conn = connect(db_path)
    row = conn.execute(
        "SELECT published FROM event_outbox WHERE run_id='run-bad' AND seq=0"
    ).fetchone()
    conn.close()
    assert row["published"] == 1  # marked handled, won't be retried forever


def test_drain_once_is_a_noop_when_outbox_is_empty(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    publisher = OutboxPublisher(db_path, kafka_broker)

    assert publisher.drain_once() == 0
