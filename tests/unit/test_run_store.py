import json
import threading
from pathlib import Path

import pytest
from pydantic import ValidationError

from engineering_team.runs import ApplyResult, RunPhase, RunSnapshot, RunStore, StoredEvent


def test_store_reloads_snapshot_and_replays_only_events_after_cursor(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.QUEUED, source_hashes={"app.py": "abc"},
    ))
    first = store.append_event("run-a", {"name": "Product", "agent": "product"})
    second = store.append_event("run-a", {"name": "Developer", "agent": "developer"})

    restarted = RunStore(tmp_path)

    assert first.sequence == 1
    assert second.sequence == 2
    assert [item.sequence for item in restarted.events_after("run-a", 1)] == [2]
    assert restarted.load("run-a").message == "change one thing"


def test_store_loads_legacy_snapshot_with_safe_run_mode_defaults(tmp_path: Path) -> None:
    legacy = RunSnapshot(
        run_id="run-legacy", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.QUEUED, source_hashes={},
    ).model_dump(mode="json")
    legacy.pop("test_spec", None)
    legacy.pop("authorize_writes", None)
    records = tmp_path / "_records"
    records.mkdir()
    (records / "run-legacy.json").write_text(json.dumps(legacy), encoding="utf-8")

    snapshot = RunStore(tmp_path).load("run-legacy")

    assert snapshot.test_spec is None
    assert snapshot.authorize_writes is False


def test_store_rejects_applying_before_approval(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={},
    ))

    with pytest.raises(ValueError, match="running -> applying"):
        store.transition("run-a", RunPhase.APPLYING)


def test_finish_persists_terminal_report_and_lists_summary(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={},
    ))

    store.finish("run-a", {"review": {"status": "APPROVED"}}, RunPhase.APPROVED)

    restarted = RunStore(tmp_path)
    assert restarted.load("run-a").report == {"review": {"status": "APPROVED"}}
    assert restarted.load("run-a").phase is RunPhase.APPROVED
    assert [summary.run_id for summary in restarted.list_summaries()] == ["run-a"]


def test_finish_populates_changed_paths_when_provided(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={},
    ))

    finished = store.finish(
        "run-a", {"review": {"status": "APPROVED"}}, RunPhase.APPROVED,
        changed_paths=["app/service.py"],
    )

    assert finished.changed_paths == ["app/service.py"]
    restarted = RunStore(tmp_path)
    assert restarted.load("run-a").changed_paths == ["app/service.py"]


def test_finish_leaves_changed_paths_untouched_when_omitted(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={}, changed_paths=["preexisting.py"],
    ))

    finished = store.finish("run-a", {"review": {"status": "APPROVED"}}, RunPhase.APPROVED)

    assert finished.changed_paths == ["preexisting.py"]


@pytest.mark.parametrize("phase", [RunPhase.QUEUED, RunPhase.PREPARING])
def test_run_can_fail_directly_before_execution(tmp_path: Path, phase: RunPhase) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=phase, source_hashes={},
    ))

    failed = store.finish(
        "run-a",
        {"review": {"status": "HUMAN_REVIEW_REQUIRED"}},
        RunPhase.FAILED,
    )

    assert failed.phase is RunPhase.FAILED
    assert RunStore(tmp_path).load("run-a").phase is RunPhase.FAILED


def test_wait_after_returns_event_published_while_waiting(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={},
    ))
    ready = threading.Event()
    received = []

    def wait_for_event() -> None:
        ready.set()
        received.extend(store.wait_after("run-a", 0, timeout=1))

    waiter = threading.Thread(target=wait_for_event)
    waiter.start()
    assert ready.wait(timeout=1)
    store.append_event("run-a", {"name": "Product", "agent": "product"})
    waiter.join(timeout=1)

    assert not waiter.is_alive()
    assert [event.sequence for event in received] == [1]


def test_restore_transition_requires_restored_audit_result(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.APPLY_FAILED, source_hashes={},
        apply_result=ApplyResult(status="apply_failed", message="verification failed"),
    ))

    with pytest.raises(ValueError, match="apply_failed -> approved"):
        store.transition("run-a", RunPhase.APPROVED)

    store.create(RunSnapshot(
        run_id="run-b", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.APPLY_FAILED, source_hashes={},
        apply_result=ApplyResult(status="restored", message="restored from backup"),
    ))

    assert store.transition("run-b", RunPhase.APPROVED).phase is RunPhase.APPROVED


def test_recorded_restore_audit_persists_before_reapproval(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.APPLY_FAILED, source_hashes={},
        apply_result=ApplyResult(status="apply_failed", message="verification failed"),
    ))

    store.record_apply_result(
        "run-a", ApplyResult(status="restored", message="restored from backup"),
    )
    store.transition("run-a", RunPhase.APPROVED)

    restored = RunStore(tmp_path).load("run-a")
    assert restored.phase is RunPhase.APPROVED
    assert restored.apply_result is not None
    assert restored.apply_result.status == "restored"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda store: store.transition("run-a", RunPhase.APPROVED),
        lambda store: store.append_event("run-a", {"name": "Product"}),
        lambda store: store.record_apply_result(
            "run-a", ApplyResult(status="applied", message="applied"),
        ),
        lambda store: store.finish("run-a", {"review": {"status": "APPROVED"}}, RunPhase.APPROVED),
    ],
    ids=["transition", "append_event", "record_apply_result", "finish"],
)
def test_failed_persistence_does_not_publish_in_memory_mutation(tmp_path: Path, monkeypatch, mutation) -> None:
    store = RunStore(tmp_path)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="change one thing",
        phase=RunPhase.RUNNING, source_hashes={},
    ))
    before = store.load("run-a")

    def fail_persist(_: RunSnapshot) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(store, "_persist", fail_persist)

    with pytest.raises(OSError, match="disk unavailable"):
        mutation(store)

    assert store.load("run-a") == before


def test_models_reject_coercible_field_values() -> None:
    with pytest.raises(ValidationError, match="valid integer"):
        StoredEvent(sequence="1", payload={})
