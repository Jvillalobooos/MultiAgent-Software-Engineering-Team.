# Persistencia y backbone de Kafka (Fase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every `RunEvent` a durable, replayable path — SQLite outbox → Kafka (`engineering.run-events.v1`) → a deduplicating projector back into SQLite (`run_events` + `event_payloads`) — so a future FastAPI/SSE layer (Fase 2b) has a real, ordered, crash-safe read model to serve from, without inferring anything from Langfuse.

**Architecture:** `SqliteOutboxEventSink` implements Phase 1's `RunEventSink` protocol and is the only thing that touches `event_outbox` — one INSERT per event, in its own transaction, and it never raises (matches the protocol's documented contract: "A sink never blocks or fails the run"). A background `OutboxPublisher` thread drains `event_outbox` and publishes to Kafka with an idempotent producer; anything that fails to serialize/validate goes to `engineering.run-dlq.v1` instead, and is still marked handled so the publisher doesn't retry forever. A background `RunEventProjector` thread consumes `engineering.run-events.v1` in consumer group `engineering-ui-projector-v1`, dedupes by `(run_id, seq)` against `run_events`, and — only after that SQLite write succeeds — commits the Kafka offset (manual commit, `enable.auto.commit=False`), giving at-least-once delivery with an idempotent write on the SQLite side. The projector also splits each event: the slim public fields go into `run_events`, and `payload` (if present) is externalized into `event_payloads` keyed by `(run_id, seq)`, with `payload_ref` on the stored event set to `"{run_id}:{seq}"` — this is what finally gives Phase 1's always-`None` `payload_ref` a real value. This phase does not touch FastAPI, SSE, the scheduler, or Apply — those are Fase 2b and Fase 4, planned separately once this phase's tests pass.

**Tech Stack:** Python 3.10+, `sqlite3` (stdlib, WAL mode), `confluent-kafka>=2.3,<3`, a local single-broker Kafka (KRaft mode) via Docker Compose for tests, pytest.

**Spec:** [docs/superpowers/specs/2026-08-27-backend-frontend-integration-design.md](../specs/2026-08-27-backend-frontend-integration-design.md) — sections 2 (event/table shapes), 3.2 (this phase), 7.2.

## Global Constraints

- SQLite tables per spec §3.2: `projects, runs, event_outbox, run_events, event_payloads, apply_intents`. This phase creates all six (so later phases don't need schema-migration tasks of their own) but only writes to `event_outbox`, `run_events`, and `event_payloads` — `projects`/`runs`/`apply_intents` are created empty, owned by Fase 2b/4.
- "Insertar seq y outbox en una transacción" (spec §3.2) — the event already carries its own `seq` (assigned in-process by Phase 1's shared counter); this phase's job is inserting that `seq` and the event into `event_outbox` as one atomic SQLite transaction, not re-deriving `seq` from the database.
- Kafka topic `engineering.run-events.v1`, keyed by `run_id`, **6 partitions**; invalid/unparseable events go to `engineering.run-dlq.v1` (spec §3.2).
- Idempotent producer, `acks=all` (spec §3.2).
- Consumer group `engineering-ui-projector-v1` commits offsets **after** the SQLite write, deduplicating by `(run_id, seq)` (spec §3.2) — never commit-then-write.
- `RunEventSink.emit()` must never raise or block the calling run (documented contract already in `src/engineering_team/observability/events.py`) — `SqliteOutboxEventSink` must catch and swallow its own errors.
- Do not modify `graph/stategraph.py`, `llm/runtime.py`, `llm/cloud.py`, `mcp/repository.py`, or any Phase 1 file under `observability/` (`events.py`, `event_trace.py`, `event_callbacks.py`, `langfuse.py`) — this phase only adds a new `RunEventSink` implementation, it does not change the sink protocol or how Phase 1 code calls it.
- `pyproject.toml`: bump `langgraph` floor to `>=1.1,<2` and the `observability` extra's `langfuse` floor to `>=4.7,<5` (already-installed versions in this repo — 1.2.11 and 4.14.5 respectively — already satisfy both; this is a metadata correction, not a new install). Add a new `ui` extra: `fastapi>=0.115`, `uvicorn>=0.30`, `confluent-kafka>=2.3,<3`.
- No FastAPI, SSE, scheduler, or Apply code in this phase.

---

### Task 1: SQLite schema and connection helper

**Files:**
- Create: `src/engineering_team/persistence/__init__.py`
- Create: `src/engineering_team/persistence/schema.py`
- Create: `src/engineering_team/persistence/db.py`
- Test: `tests/unit/test_persistence_schema.py`
- Modify: `pyproject.toml` (bump `langgraph`/`langfuse` floors, add `ui` extra)

**Interfaces:**
- Produces: `migrate(db_path: str | Path) -> None` (creates all 6 tables + `schema_version` if missing, idempotent), `connect(db_path: str | Path) -> sqlite3.Connection` (opens with WAL mode, `row_factory=sqlite3.Row`, foreign keys off) — used by every later task in this plan.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_persistence_schema.py
import sqlite3

from engineering_team.persistence.db import connect
from engineering_team.persistence.schema import migrate


def test_migrate_creates_all_tables(tmp_path):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)

    conn = connect(db_path)
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert {
        "projects", "runs", "event_outbox", "run_events",
        "event_payloads", "apply_intents", "schema_version",
    } <= tables


def test_migrate_is_idempotent(tmp_path):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    migrate(db_path)  # must not raise on a second call

    conn = connect(db_path)
    version = conn.execute("SELECT version FROM schema_version").fetchone()
    conn.close()
    assert version["version"] == 1


def test_connect_opens_wal_mode(tmp_path):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)

    conn = connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"


def test_event_outbox_enforces_unique_run_id_seq(tmp_path):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    conn = connect(db_path)
    conn.execute(
        "INSERT INTO event_outbox (run_id, seq, event_json, created_at) "
        "VALUES ('r1', 0, '{}', '2026-01-01T00:00:00Z')"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO event_outbox (run_id, seq, event_json, created_at) "
            "VALUES ('r1', 0, '{}', '2026-01-01T00:00:01Z')"
        )
        conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    finally:
        conn.close()
    assert raised
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_persistence_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.persistence'`

- [ ] **Step 3: Write `db.py`**

```python
# src/engineering_team/persistence/db.py
"""Thin sqlite3 connection helper shared by every persistence/Kafka component."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn
```

- [ ] **Step 4: Write `schema.py`**

```python
# src/engineering_team/persistence/schema.py
"""SQLite DDL for the engineering-team persistence layer (Fase 2)."""

from __future__ import annotations

from pathlib import Path

from .db import connect

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    last_used_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    specification TEXT NOT NULL,
    test_specification TEXT,
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('DRY_RUN','STAGED_WRITE')),
    phase TEXT NOT NULL CHECK(phase IN (
        'QUEUED','PREFLIGHT','RUNNING','WAITING_HUMAN','FINALIZING',
        'COMPLETED','FAILED','INTERRUPTED'
    )),
    outcome TEXT CHECK(outcome IN (
        'APPROVED','HUMAN_REVIEW_REQUIRED','TERMINATED','FAILED'
    ) OR outcome IS NULL),
    apply_status TEXT NOT NULL DEFAULT 'NOT_ELIGIBLE' CHECK(apply_status IN (
        'NOT_ELIGIBLE','READY','APPLYING','APPLIED','CONFLICT','APPLY_FAILED'
    )),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_outbox (
    outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    published INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, seq)
);

CREATE TABLE IF NOT EXISTS run_events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS event_payloads (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS apply_intents (
    run_id TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    fingerprint_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


def migrate(db_path: str | Path) -> None:
    """Create every table this phase needs, if not already present. Idempotent."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        conn.executescript(_DDL)
        existing = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        if existing == 0:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 5: Bump `pyproject.toml`**

In `pyproject.toml`, change the `langgraph` line inside `[project] dependencies` from `"langgraph>=0.2,<2",` to `"langgraph>=1.1,<2",`. Change the `observability` extra from `observability = ["langfuse>=4.0,<5"]` to `observability = ["langfuse>=4.7,<5"]`. Add a new extra right after `sample-app`:

```toml
ui = ["fastapi>=0.115", "uvicorn>=0.30", "confluent-kafka>=2.3,<3"]
```

Then install it: `.venv/bin/pip install -e ".[dev,rag,observability,sample-app,ui]"`

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_persistence_schema.py -v`
Expected: PASS (4 passed)

- [ ] **Step 7: Commit**

```bash
git add src/engineering_team/persistence/__init__.py src/engineering_team/persistence/schema.py src/engineering_team/persistence/db.py tests/unit/test_persistence_schema.py pyproject.toml
git commit -m "feat: add SQLite schema and connection helper for Fase 2 persistence"
```

---

### Task 2: `SqliteOutboxEventSink`

**Files:**
- Create: `src/engineering_team/persistence/outbox_sink.py`
- Test: `tests/unit/test_outbox_sink.py`

**Interfaces:**
- Consumes: `RunEventSink` protocol, `RunEvent` (`observability/events.py`, `contracts/models.py` — Phase 1, unchanged), `connect`/`migrate` (Task 1).
- Produces: `SqliteOutboxEventSink(db_path: str | Path)` with `.emit(event: RunEvent) -> None`, satisfying `RunEventSink` structurally — this is what Task 6's end-to-end test (and, later, Fase 2b's API layer) passes as `event_sink=` to `run_on_project`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_outbox_sink.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_outbox_sink.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.persistence.outbox_sink'`

- [ ] **Step 3: Write the implementation**

```python
# src/engineering_team/persistence/outbox_sink.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_outbox_sink.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/persistence/outbox_sink.py tests/unit/test_outbox_sink.py
git commit -m "feat: add SqliteOutboxEventSink"
```

---

### Task 3: Kafka topics module and local dev broker

**Files:**
- Create: `src/engineering_team/kafka/__init__.py`
- Create: `src/engineering_team/kafka/topics.py`
- Create: `docker-compose.kafka.yml`
- Create: `tests/integration/conftest.py` (a shared `kafka_broker` fixture used by Tasks 4-6)
- Test: `tests/integration/test_kafka_topics.py`

**Interfaces:**
- Produces: `RUN_EVENTS_TOPIC = "engineering.run-events.v1"`, `RUN_DLQ_TOPIC = "engineering.run-dlq.v1"`, `PARTITION_COUNT = 6` (`kafka/topics.py`) — used by Tasks 4-6. `ensure_topics(bootstrap_servers: str) -> None`, idempotent topic creation, used by the `kafka_broker` pytest fixture and reusable by a future startup path.
- Produces: a pytest fixture `kafka_broker` (`tests/integration/conftest.py`) yielding the bootstrap-servers string (`"localhost:9092"`) after confirming the broker is reachable, and `pytest.skip`-ing the test if it is not — every Kafka-touching test in Tasks 4-6 uses this fixture instead of hardcoding connectivity assumptions.

This task requires a locally running Kafka broker to pass its own test — start it first:

```bash
docker compose -f docker-compose.kafka.yml up -d
```

- [ ] **Step 1: Write `docker-compose.kafka.yml`**

```yaml
# docker-compose.kafka.yml
# Single-node Kafka (KRaft mode, no Zookeeper) for local development and
# integration tests. Loopback-only — matches the spec's "broker ligado a
# loopback" requirement; not for production use.
services:
  kafka:
    image: apache/kafka:4.2.1
    container_name: engineering-team-kafka
    ports:
      - "127.0.0.1:9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://127.0.0.1:9092
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@localhost:9093
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_LOG_RETENTION_HOURS: 720
```

- [ ] **Step 2: Write `kafka/topics.py`**

```python
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
    for name, future in futures.items():
        future.result(timeout=timeout_seconds)  # raises on failure
```

- [ ] **Step 3: Write the shared `kafka_broker` fixture**

```python
# tests/integration/conftest.py
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
```

- [ ] **Step 4: Write the failing test, then confirm it passes against a real broker**

```python
# tests/integration/test_kafka_topics.py
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
```

Before writing `kafka/topics.py` this test fails with `ModuleNotFoundError`. Run: `.venv/bin/python -m pytest tests/integration/test_kafka_topics.py -v` first to confirm that RED, then add the two files above and confirm GREEN:

Run: `docker compose -f docker-compose.kafka.yml up -d` (wait ~10s for the broker to be ready), then `.venv/bin/python -m pytest tests/integration/test_kafka_topics.py -v`
Expected: PASS (2 passed). If it skips with "no Kafka broker reachable", the broker isn't up yet — wait longer or check `docker compose -f docker-compose.kafka.yml logs kafka`.

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/kafka/__init__.py src/engineering_team/kafka/topics.py docker-compose.kafka.yml tests/integration/conftest.py tests/integration/test_kafka_topics.py
git commit -m "feat: add Kafka topics module and local dev broker compose file"
```

---

### Task 4: `OutboxPublisher`

**Files:**
- Create: `src/engineering_team/kafka/producer.py`
- Test: `tests/integration/test_outbox_publisher.py`

**Interfaces:**
- Consumes: `RUN_EVENTS_TOPIC`, `RUN_DLQ_TOPIC` (Task 3), `connect` (Task 1), the `kafka_broker` fixture (Task 3).
- Produces: `OutboxPublisher(db_path, bootstrap_servers)` with `.drain_once() -> int` (publishes every currently-unpublished outbox row, returns the count published) and `.run_forever(poll_interval_seconds: float = 1.0) -> None` (loops `drain_once` with a stop mechanism — see `.stop()`) — `.run_forever`/`.stop()` are exercised in Task 6's end-to-end test as a background thread; Task 4's own tests use `.drain_once()` directly for determinism.

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_outbox_publisher.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_outbox_publisher.py -v` (with the broker up per Task 3)
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.kafka.producer'`

- [ ] **Step 3: Write the implementation**

```python
# src/engineering_team/kafka/producer.py
"""Drains event_outbox into Kafka with an idempotent producer.

Every row gets published exactly once (per outbox row) and is marked
`published=1` afterward regardless of whether it went to the real topic or
the DLQ — a row that can't be parsed must not be retried forever.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from confluent_kafka import Producer

from .topics import RUN_DLQ_TOPIC, RUN_EVENTS_TOPIC
from ..persistence.db import connect


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/test_outbox_publisher.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/kafka/producer.py tests/integration/test_outbox_publisher.py
git commit -m "feat: add OutboxPublisher"
```

---

### Task 5: `RunEventProjector`

**Files:**
- Create: `src/engineering_team/kafka/projector.py`
- Test: `tests/integration/test_run_event_projector.py`

**Interfaces:**
- Consumes: `RUN_EVENTS_TOPIC` (Task 3), `connect` (Task 1), `RunEvent` (Phase 1).
- Produces: `RunEventProjector(db_path, bootstrap_servers)` with `.poll_once(timeout_seconds: float = 5.0) -> int` (consumes and projects up to one batch, returns count projected) and `.run_forever(poll_interval_seconds: float = 1.0) -> None` / `.stop()` (same shape as `OutboxPublisher`, used together in Task 6).

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_run_event_projector.py
import json
import uuid

from confluent_kafka import Producer

from engineering_team.kafka.projector import RunEventProjector
from engineering_team.kafka.topics import RUN_EVENTS_TOPIC
from engineering_team.persistence.db import connect
from engineering_team.persistence.schema import migrate


def _produce_raw_event(bootstrap_servers: str, run_id: str, seq: int, payload=None) -> None:
    producer = Producer({"bootstrap.servers": bootstrap_servers, "enable.idempotence": True, "acks": "all"})
    body = {
        "schema_version": 1, "event_id": str(uuid.uuid4()), "run_id": run_id, "seq": seq,
        "trace_id": "t1", "kind": "NODE_STARTED", "timestamp": "2026-01-01T00:00:00Z",
        "agent": "Product", "iteration": None, "status": None,
        "summary": "Product started", "metrics": {}, "payload": payload, "payload_ref": None,
    }
    producer.produce(RUN_EVENTS_TOPIC, key=run_id, value=json.dumps(body).encode("utf-8"))
    producer.flush(timeout=10.0)


def test_poll_once_projects_a_new_event_into_run_events(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    run_id = f"run-proj-{uuid.uuid4()}"
    _produce_raw_event(kafka_broker, run_id, 0)

    projector = RunEventProjector(db_path, kafka_broker)
    projected = projector.poll_once(timeout_seconds=10.0)

    assert projected == 1
    conn = connect(db_path)
    row = conn.execute(
        "SELECT event_json FROM run_events WHERE run_id = ? AND seq = 0", (run_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    stored = json.loads(row["event_json"])
    assert stored["summary"] == "Product started"


def test_poll_once_dedupes_a_redelivered_event(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    run_id = f"run-dedupe-{uuid.uuid4()}"
    _produce_raw_event(kafka_broker, run_id, 0)

    projector = RunEventProjector(db_path, kafka_broker)
    projector.poll_once(timeout_seconds=10.0)
    # Simulate redelivery: same event, same (run_id, seq), produced again.
    _produce_raw_event(kafka_broker, run_id, 0)
    projector.poll_once(timeout_seconds=10.0)

    conn = connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) AS n FROM run_events WHERE run_id = ? AND seq = 0", (run_id,)
    ).fetchone()["n"]
    conn.close()
    assert count == 1


def test_poll_once_externalizes_payload_into_event_payloads_and_sets_payload_ref(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    run_id = f"run-payload-{uuid.uuid4()}"
    _produce_raw_event(kafka_broker, run_id, 0, payload={"input": "hi", "output": "hello"})

    projector = RunEventProjector(db_path, kafka_broker)
    projector.poll_once(timeout_seconds=10.0)

    conn = connect(db_path)
    event_row = conn.execute(
        "SELECT event_json FROM run_events WHERE run_id = ? AND seq = 0", (run_id,)
    ).fetchone()
    payload_row = conn.execute(
        "SELECT payload_json FROM event_payloads WHERE run_id = ? AND seq = 0", (run_id,)
    ).fetchone()
    conn.close()

    stored_event = json.loads(event_row["event_json"])
    assert stored_event["payload"] is None  # stripped from the slim event
    assert stored_event["payload_ref"] == f"{run_id}:0"
    assert json.loads(payload_row["payload_json"]) == {"input": "hi", "output": "hello"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_run_event_projector.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.kafka.projector'`

- [ ] **Step 3: Write the implementation**

```python
# src/engineering_team/kafka/projector.py
"""Consumes engineering.run-events.v1 and materializes the SQLite read model.

Commits the Kafka offset only after the SQLite write succeeds (manual
commit, enable.auto.commit=False) — a crash between those two steps causes
redelivery, and the (run_id, seq) primary key on run_events makes that
redelivery a harmless no-op (INSERT OR IGNORE) rather than a duplicate.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from confluent_kafka import Consumer

from .topics import RUN_EVENTS_TOPIC
from ..persistence.db import connect

_GROUP_ID = "engineering-ui-projector-v1"


class RunEventProjector:
    def __init__(self, db_path: str | Path, bootstrap_servers: str) -> None:
        self._db_path = Path(db_path)
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": _GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        self._consumer.subscribe([RUN_EVENTS_TOPIC])
        self._stop_event = threading.Event()

    def poll_once(self, timeout_seconds: float = 5.0) -> int:
        msg = self._consumer.poll(timeout_seconds)
        if msg is None or msg.error() is not None:
            return 0
        event = json.loads(msg.value())
        self._project(event)
        self._consumer.commit(message=msg, asynchronous=False)
        return 1

    def _project(self, event: dict) -> None:
        run_id, seq = event["run_id"], event["seq"]
        payload = event.get("payload")
        now = datetime.now(UTC).isoformat()
        conn = connect(self._db_path)
        try:
            existing = conn.execute(
                "SELECT 1 FROM run_events WHERE run_id = ? AND seq = ?", (run_id, seq)
            ).fetchone()
            if existing is not None:
                return  # already projected — redelivery, harmless no-op
            if payload is not None:
                conn.execute(
                    "INSERT OR IGNORE INTO event_payloads (run_id, seq, payload_json) "
                    "VALUES (?, ?, ?)",
                    (run_id, seq, json.dumps(payload)),
                )
                event = {**event, "payload": None, "payload_ref": f"{run_id}:{seq}"}
            conn.execute(
                "INSERT INTO run_events (run_id, seq, event_json, inserted_at) "
                "VALUES (?, ?, ?, ?)",
                (run_id, seq, json.dumps(event), now),
            )
            conn.commit()
        finally:
            conn.close()

    def run_forever(self, poll_interval_seconds: float = 1.0) -> None:
        while not self._stop_event.is_set():
            self.poll_once(timeout_seconds=poll_interval_seconds)

    def stop(self) -> None:
        self._stop_event.set()
        self._consumer.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/test_run_event_projector.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/kafka/projector.py tests/integration/test_run_event_projector.py
git commit -m "feat: add RunEventProjector"
```

---

### Task 6: End-to-end wiring test

**Files:**
- Test: `tests/integration/test_persistence_kafka_end_to_end.py`

**Interfaces:**
- Consumes: `SqliteOutboxEventSink` (Task 2), `OutboxPublisher` (Task 4), `RunEventProjector` (Task 5) — no new production code, this task only proves the pieces work together as background threads the way Fase 2b will actually run them.

- [ ] **Step 1: Write the test**

```python
# tests/integration/test_persistence_kafka_end_to_end.py
import json
import threading
import time
import uuid

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.kafka.producer import OutboxPublisher
from engineering_team.kafka.projector import RunEventProjector
from engineering_team.persistence.db import connect
from engineering_team.persistence.outbox_sink import SqliteOutboxEventSink
from engineering_team.persistence.schema import migrate


def _event(run_id: str, seq: int, kind: RunEventKind, summary: str) -> RunEvent:
    return RunEvent(
        event_id=str(uuid.uuid4()), run_id=run_id, seq=seq, trace_id="t1",
        kind=kind, agent="Product", iteration=None, status=None,
        summary=summary, metrics={},
    )


def test_emit_to_outbox_to_kafka_to_projector_end_to_end(tmp_path, kafka_broker):
    db_path = tmp_path / "engineering.db"
    migrate(db_path)
    run_id = f"run-e2e-{uuid.uuid4()}"

    sink = SqliteOutboxEventSink(db_path)
    publisher = OutboxPublisher(db_path, kafka_broker)
    projector = RunEventProjector(db_path, kafka_broker)

    publisher_thread = threading.Thread(target=publisher.run_forever, args=(0.2,), daemon=True)
    projector_thread = threading.Thread(target=projector.run_forever, args=(0.2,), daemon=True)
    publisher_thread.start()
    projector_thread.start()

    try:
        events = [
            _event(run_id, 0, RunEventKind.RUN_STARTED, "run started"),
            _event(run_id, 1, RunEventKind.NODE_STARTED, "Product started"),
            _event(run_id, 2, RunEventKind.NODE_FINISHED, "Product finished"),
            _event(run_id, 3, RunEventKind.RUN_FINISHED, "run finished"),
        ]
        for event in events:
            sink.emit(event)

        deadline = time.monotonic() + 20.0
        projected_count = 0
        while time.monotonic() < deadline:
            conn = connect(db_path)
            projected_count = conn.execute(
                "SELECT COUNT(*) AS n FROM run_events WHERE run_id = ?", (run_id,)
            ).fetchone()["n"]
            conn.close()
            if projected_count == len(events):
                break
            time.sleep(0.5)

        assert projected_count == len(events), (
            f"expected {len(events)} projected events within 20s, got {projected_count}"
        )

        conn = connect(db_path)
        rows = conn.execute(
            "SELECT seq, event_json FROM run_events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
        conn.close()
        summaries = [json.loads(row["event_json"])["summary"] for row in rows]
        assert summaries == ["run started", "Product started", "Product finished", "run finished"]
    finally:
        publisher.stop()
        projector.stop()
        publisher_thread.join(timeout=5.0)
        projector_thread.join(timeout=5.0)
```

- [ ] **Step 2: Run it against the real broker**

Run: `.venv/bin/python -m pytest tests/integration/test_persistence_kafka_end_to_end.py -v -s`
Expected: PASS (1 passed) within the 20s deadline. If it times out, check `docker compose -f docker-compose.kafka.yml logs kafka` for broker issues before assuming a code bug.

- [ ] **Step 3: Run the full suite and lint**

Run: `.venv/bin/python -m pytest -q --deselect tests/e2e/test_multimodel_evidence.py::test_one_normal_run_invokes_both_local_models_through_router`
Run: `.venv/bin/python -m ruff check src/ tests/`
Expected: both clean. Note the new `tests/integration/test_kafka_topics.py`, `test_outbox_publisher.py`, `test_run_event_projector.py`, and this task's test all require the Kafka broker from Task 3 to be running — if it isn't, they skip (via the `kafka_broker` fixture) rather than fail, so the deselected-only full-suite run above should still pass either way.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_persistence_kafka_end_to_end.py
git commit -m "test: add end-to-end SqliteOutboxEventSink -> Kafka -> RunEventProjector coverage"
```

---

## Out of scope for this phase (Fase 2b / Fase 4)

- FastAPI app, all 9 REST endpoints, SSE delivery with `Last-Event-ID` replay.
- The single-run-at-a-time scheduler thread and `runs`/`projects` table CRUD (the tables exist from Task 1, but nothing writes to them yet — Fase 2b owns that).
- Serving the frontend build from FastAPI.
- Apply staging, tokens, `apply_intents` usage (the table exists from Task 1, empty).
- A production-hardened Docker Compose (retention tuning beyond the 30-day default set here, DLQ topic alerting, etc.) — this phase's `docker-compose.kafka.yml` is a working dev/test broker, not the final deployment artifact.
