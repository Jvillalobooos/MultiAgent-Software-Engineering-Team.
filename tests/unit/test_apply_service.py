from __future__ import annotations

import json
from pathlib import Path

import pytest

from engineering_team.apply_service import ApplyService, safe_target, snapshot_project
from engineering_team.runs import RunPhase, RunSnapshot, RunStore


class PassingVerification:
    def run(self, project: Path) -> tuple[int, str]:
        return 0, "24 passed"


class FailingVerification:
    def run(self, project: Path) -> tuple[int, str]:
        return 1, "1 failed"


def approved_store(root: Path, source: Path, workspace: Path, paths: list[str]) -> RunStore:
    store = RunStore(root)
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes=snapshot_project(source),
        changed_paths=paths, report={"review": {"status": "APPROVED"}},
    ))
    return store


def test_apply_writes_workspace_content_and_keeps_backup(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=PassingVerification())

    result = service.apply("run-a", confirmed_project=source)

    assert (source / "app.py").read_text(encoding="utf-8") == "new\n"
    assert (Path(result.backup_path) / "app.py").read_text(encoding="utf-8") == "old\n"
    assert result.status == "applied"
    assert result.written_paths == ["app.py"]
    assert store.load("run-a").phase is RunPhase.APPLIED


def test_apply_blocks_when_source_changed_after_run_started(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("agent\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=PassingVerification())
    (source / "app.py").write_text("human\n", encoding="utf-8")

    result = service.apply("run-a", confirmed_project=source)

    assert result.status == "conflict"
    assert (source / "app.py").read_text(encoding="utf-8") == "human\n"
    assert store.load("run-a").phase is RunPhase.APPROVED


def test_apply_creates_new_file_that_did_not_previously_exist(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (workspace / "new_module.py").write_text("value = 1\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["new_module.py"])
    service = ApplyService(store, verification=PassingVerification())

    result = service.apply("run-a", confirmed_project=source)

    assert result.status == "applied"
    assert (source / "new_module.py").read_text(encoding="utf-8") == "value = 1\n"
    manifest = json.loads((Path(result.backup_path) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["new_module.py"]["existed"] is False


def test_apply_rolls_back_automatically_when_write_fails(tmp_path: Path, monkeypatch) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "a.py").write_text("old-a\n", encoding="utf-8")
    (source / "b.py").write_text("old-b\n", encoding="utf-8")
    (workspace / "a.py").write_text("new-a\n", encoding="utf-8")
    (workspace / "b.py").write_text("new-b\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["a.py", "b.py"])
    service = ApplyService(store, verification=PassingVerification())

    import engineering_team.apply_service as apply_service_module

    original_replace = Path.replace
    calls = {"count": 0}

    def flaky_replace(self: Path, target: Path) -> Path:
        calls["count"] += 1
        if self.name.startswith(".nova-") and calls["count"] == 2:
            raise OSError("disk full")
        return original_replace(self, target)

    monkeypatch.setattr(apply_service_module.Path, "replace", flaky_replace)

    result = service.apply("run-a", confirmed_project=source)

    assert result.status == "apply_failed"
    assert (source / "a.py").read_text(encoding="utf-8") == "old-a\n"
    assert (source / "b.py").read_text(encoding="utf-8") == "old-b\n"
    assert store.load("run-a").phase is RunPhase.APPLY_FAILED
    assert result.backup_path is None

    with pytest.raises(ValueError):
        service.restore("run-a")


def test_apply_fails_cleanly_when_workspace_file_is_missing(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "a.py").write_text("old-a\n", encoding="utf-8")
    (workspace / "a.py").write_text("new-a\n", encoding="utf-8")
    # "missing.py" is listed as changed but was never materialized in the workspace.
    store = approved_store(tmp_path / "records", source, workspace, ["a.py", "missing.py"])
    service = ApplyService(store, verification=PassingVerification())

    result = service.apply("run-a", confirmed_project=source)

    assert result.status == "apply_failed"
    assert "missing.py" in result.message
    assert (source / "a.py").read_text(encoding="utf-8") == "old-a\n"
    assert not (source / "missing.py").exists()
    assert result.backup_path is None
    assert store.load("run-a").phase is RunPhase.APPLY_FAILED


def test_apply_keeps_written_files_and_offers_restore_when_verification_fails(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=FailingVerification())

    result = service.apply("run-a", confirmed_project=source)

    assert result.status == "apply_failed"
    assert result.test_exit_code == 1
    assert (source / "app.py").read_text(encoding="utf-8") == "new\n"
    assert store.load("run-a").phase is RunPhase.APPLY_FAILED

    restored = service.restore("run-a")

    assert restored.status == "restored"
    assert (source / "app.py").read_text(encoding="utf-8") == "old\n"
    assert store.load("run-a").phase is RunPhase.APPROVED


def test_restore_rejects_source_edited_after_apply(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=FailingVerification())
    service.apply("run-a", confirmed_project=source)
    (source / "app.py").write_text("human-edit\n", encoding="utf-8")

    result = service.restore("run-a")

    assert result.status == "conflict"
    assert (source / "app.py").read_text(encoding="utf-8") == "human-edit\n"
    assert store.load("run-a").phase is RunPhase.APPLY_FAILED


def test_apply_is_idempotent_and_does_not_rewrite_on_repeat(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=PassingVerification())
    first = service.apply("run-a", confirmed_project=source)
    mtime_before = (source / "app.py").stat().st_mtime_ns

    second = service.apply("run-a", confirmed_project=source)

    assert second == first
    assert (source / "app.py").stat().st_mtime_ns == mtime_before


def test_restore_is_idempotent_on_repeat(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, ["app.py"])
    service = ApplyService(store, verification=FailingVerification())
    service.apply("run-a", confirmed_project=source)
    first = service.restore("run-a")

    second = service.restore("run-a")

    assert second == first


def test_snapshot_project_skips_ignored_directories(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / ".git").mkdir(parents=True)
    (project / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (project / ".venv" / "lib").mkdir(parents=True)
    (project / ".venv" / "lib" / "x.py").write_text("x", encoding="utf-8")
    (project / "__pycache__").mkdir(parents=True)
    (project / "__pycache__" / "y.pyc").write_bytes(b"y")
    (project / "workspace" / "runs").mkdir(parents=True)
    (project / "workspace" / "runs" / "z.json").write_text("z", encoding="utf-8")
    (project / "rag" / "chroma").mkdir(parents=True)
    (project / "rag" / "chroma" / "index").write_text("i", encoding="utf-8")
    (project / "app.py").write_text("value = 1\n", encoding="utf-8")

    hashes = snapshot_project(project)

    assert set(hashes) == {"app.py"}


def test_snapshot_project_skips_backup_and_record_directories(tmp_path: Path) -> None:
    """If the workspace root overlaps the selected project, backups/records must not
    be hashed into conflict-detection fingerprints."""
    project = tmp_path / "project"
    (project / "_backups" / "run-a").mkdir(parents=True)
    (project / "_backups" / "run-a" / "app.py").write_text("old\n", encoding="utf-8")
    (project / "_records").mkdir(parents=True)
    (project / "_records" / "run-a.json").write_text("{}", encoding="utf-8")
    (project / "app.py").write_text("value = 1\n", encoding="utf-8")

    hashes = snapshot_project(project)

    assert set(hashes) == {"app.py"}


def test_safe_target_rejects_traversal_and_absolute_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError):
        safe_target(root, "../outside.py")
    with pytest.raises(ValueError):
        safe_target(root, "/etc/passwd")


def test_restore_without_prior_apply_failure_raises(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    store = approved_store(tmp_path / "records", source, workspace, [])
    service = ApplyService(store, verification=PassingVerification())

    with pytest.raises(ValueError):
        service.restore("run-a")
