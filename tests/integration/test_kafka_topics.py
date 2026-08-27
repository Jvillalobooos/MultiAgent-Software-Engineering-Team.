from confluent_kafka.admin import AdminClient

from engineering_team.kafka.topics import PARTITION_COUNT, RUN_DLQ_TOPIC, RUN_EVENTS_TOPIC


def test_ensure_topics_creates_both_topics_with_six_partitions(kafka_broker):
    admin = AdminClient({"bootstrap.servers": kafka_broker})
    metadata = admin.list_topics(timeout=5.0)

    for topic in (RUN_EVENTS_TOPIC, RUN_DLQ_TOPIC):
        assert topic in metadata.topics
        assert len(metadata.topics[topic].partitions) == PARTITION_COUNT


def test_ensure_topics_is_idempotent(kafka_broker):
    from engineering_team.kafka.topics import ensure_topics
    ensure_topics(kafka_broker)  # second call, via the fixture's own call plus this one — must not raise
