from concurrent.futures import Future
from unittest import mock

import pytest
from confluent_kafka.admin import AdminClient

from engineering_team.kafka.topics import (
    PARTITION_COUNT,
    RUN_DLQ_TOPIC,
    RUN_EVENTS_TOPIC,
    ensure_topics,
)


def test_ensure_topics_creates_both_topics_with_six_partitions(kafka_broker):
    admin = AdminClient({"bootstrap.servers": kafka_broker})
    metadata = admin.list_topics(timeout=5.0)

    for topic in (RUN_EVENTS_TOPIC, RUN_DLQ_TOPIC):
        assert topic in metadata.topics
        assert len(metadata.topics[topic].partitions) == PARTITION_COUNT


def test_ensure_topics_is_idempotent(kafka_broker):
    ensure_topics(kafka_broker)  # second call, via the fixture's own call plus this one — must not raise


def test_ensure_topics_reports_all_failed_topics_when_both_fail():
    """If both topic creations fail, the raised error must name both topics.

    Uses a mocked AdminClient (no real broker involved) because forcing two
    simultaneous creation failures against a real broker isn't practical.
    """
    failing_events_future: Future = Future()
    failing_events_future.set_exception(RuntimeError("events broker rejected it"))
    failing_dlq_future: Future = Future()
    failing_dlq_future.set_exception(RuntimeError("dlq broker rejected it"))

    mock_admin = mock.MagicMock()
    mock_admin.list_topics.return_value.topics = {}
    mock_admin.create_topics.return_value = {
        RUN_EVENTS_TOPIC: failing_events_future,
        RUN_DLQ_TOPIC: failing_dlq_future,
    }

    with mock.patch(
        "engineering_team.kafka.topics.AdminClient", return_value=mock_admin
    ), pytest.raises(RuntimeError) as exc_info:
        ensure_topics("localhost:9092")

    message = str(exc_info.value)
    assert RUN_EVENTS_TOPIC in message
    assert RUN_DLQ_TOPIC in message
