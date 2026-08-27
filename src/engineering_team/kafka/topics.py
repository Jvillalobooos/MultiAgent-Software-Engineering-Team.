# src/engineering_team/kafka/topics.py
"""Kafka topic names and idempotent topic creation."""

from __future__ import annotations

from confluent_kafka.admin import AdminClient, NewTopic

RUN_EVENTS_TOPIC = "engineering.run-events.v1"
RUN_DLQ_TOPIC = "engineering.run-dlq.v1"
PARTITION_COUNT = 6


def ensure_topics(bootstrap_servers: str, *, timeout_seconds: float = 10.0) -> None:
    """Create both topics if they don't already exist. Safe to call repeatedly."""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})
    existing = admin.list_topics(timeout=timeout_seconds).topics
    to_create = [
        NewTopic(name, num_partitions=PARTITION_COUNT, replication_factor=1)
        for name in (RUN_EVENTS_TOPIC, RUN_DLQ_TOPIC)
        if name not in existing
    ]
    if not to_create:
        return
    futures = admin.create_topics(to_create, request_timeout=timeout_seconds)
    failures: list[tuple[str, BaseException]] = []
    for name, future in futures.items():
        try:
            future.result(timeout=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - collected below, not swallowed
            failures.append((name, exc))
    if failures:
        details = "; ".join(f"{name}: {exc}" for name, exc in failures)
        raise RuntimeError(f"failed to create {len(failures)} topic(s): {details}") from failures[0][1]
