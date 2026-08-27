import pytest
from confluent_kafka.admin import AdminClient

from engineering_team.kafka.topics import ensure_topics

_BOOTSTRAP_SERVERS = "localhost:9092"


@pytest.fixture
def kafka_broker() -> str:
    """Bootstrap-servers string for a real local Kafka broker.

    Skips the test (rather than failing) if no broker is reachable — start
    one with `docker compose -f docker-compose.kafka.yml up -d` before
    running Kafka-touching tests.
    """
    admin = AdminClient({"bootstrap.servers": _BOOTSTRAP_SERVERS})
    try:
        metadata = admin.list_topics(timeout=3.0)
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means skip
        pytest.skip(f"no Kafka broker reachable at {_BOOTSTRAP_SERVERS}: {exc}")
    if not metadata.brokers:
        pytest.skip(f"no Kafka broker reachable at {_BOOTSTRAP_SERVERS}")
    ensure_topics(_BOOTSTRAP_SERVERS)
    return _BOOTSTRAP_SERVERS
