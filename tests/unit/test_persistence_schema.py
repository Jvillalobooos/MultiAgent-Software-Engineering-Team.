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
