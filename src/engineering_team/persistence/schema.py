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
