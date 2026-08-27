"""Conflict-safe application of an approved run's isolated changes to source."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

from engineering_team.runs import ApplyResult, RunPhase, RunSnapshot, RunStore

_IGNORED_DIRECTORY_NAMES = {".git", ".venv", "__pycache__", "_backups", "_records"}
_IGNORED_TWO_PART_DIRECTORIES = {("workspace", "runs"), ("rag", "chroma")}
_MANIFEST_NAME = "manifest.json"


def file_hash(path: Path) -> str | None:
    """Return the sha256 hex digest of ``path``'s contents, or ``None`` if absent."""
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot_project(root: Path) -> dict[str, str | None]:
    """Compute the canonical source fingerprint used for conflict detection."""
    hashes: dict[str, str | None] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        parts = relative.parts
        if _IGNORED_DIRECTORY_NAMES.intersection(parts):
            continue
        if len(parts) >= 2 and parts[:2] in _IGNORED_TWO_PART_DIRECTORIES:
            continue
        if path.is_symlink() or not path.is_file():
            continue
        hashes[relative.as_posix()] = file_hash(path)
    return hashes


def safe_target(root: Path, relative: str) -> Path:
    """Resolve ``relative`` under ``root``, rejecting escapes and symlinks."""
    requested = Path(relative)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("unsafe project-relative path")
    target = (root / requested).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path resolves outside project")
    if target.is_symlink():
        raise ValueError("symbolic-link targets are not writable")
    return target


class VerificationRunner(Protocol):
    def run(self, project: Path) -> tuple[int, str]: ...


class PytestVerificationRunner:
    """Runs the project's own pytest suite against the applied source tree."""

    def __init__(self, paths: list[str] | None = None) -> None:
        self.paths = paths or []

    def run(self, project: Path) -> tuple[int, str]:
        process = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", *self.paths], cwd=project,
            capture_output=True, text=True, timeout=120, check=False,
        )
        return process.returncode, (process.stdout + process.stderr)[-8000:]


class ApplyService:
    """Safely writes an approved run's isolated changes back into the source project."""

    def __init__(self, store: RunStore, verification: VerificationRunner | None = None) -> None:
        self.store = store
        self.verification = verification or PytestVerificationRunner()

    def apply(self, run_id: str, confirmed_project: Path) -> ApplyResult:
        snapshot = self.store.load(run_id)
        if snapshot.phase in (RunPhase.APPLIED, RunPhase.APPLY_FAILED) and snapshot.apply_result is not None:
            return snapshot.apply_result
        if snapshot.phase is not RunPhase.APPROVED:
            raise ValueError(f"run is not approved for apply: {snapshot.phase.value}")

        source = Path(snapshot.project_path).resolve()
        if Path(confirmed_project).resolve() != source:
            raise ValueError("confirmed_project does not match the run's project_path")
        workspace = Path(snapshot.workspace_path).resolve()

        self.store.transition(run_id, RunPhase.APPLYING)

        conflicts = self._detect_conflicts(snapshot, source)
        if conflicts:
            result = ApplyResult(
                status="conflict",
                message=f"source changed since run started: {', '.join(sorted(conflicts))}",
            )
            self.store.record_apply_result(run_id, result)
            self.store.transition(run_id, RunPhase.APPROVED)
            return result

        backup_dir = self._backup_dir(run_id)
        backup_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, dict[str, Any]] = {}
        written: list[str] = []

        try:
            for relative in snapshot.changed_paths:
                target = safe_target(source, relative)
                workspace_file = safe_target(workspace, relative)
                existed = target.exists()
                manifest[relative] = {"existed": existed}
                if existed:
                    backup_target = backup_dir / relative
                    backup_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup_target)
                if not workspace_file.exists():
                    raise FileNotFoundError(
                        f"workspace file missing for changed path: {relative}",
                    )
                content = workspace_file.read_bytes()
                self._atomic_write(run_id, target, content)
                written.append(relative)
                manifest[relative]["applied_hash"] = file_hash(target)
            (backup_dir / _MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - any write failure must roll back durably.
            self._rollback(source, backup_dir, manifest, written)
            result = ApplyResult(
                status="apply_failed",
                written_paths=[],
                backup_path=None,
                message=f"apply failed and was rolled back: {exc}",
            )
            self.store.record_apply_result(run_id, result)
            self.store.transition(run_id, RunPhase.APPLY_FAILED)
            return result

        exit_code, output = self.verification.run(source)
        if exit_code != 0:
            result = ApplyResult(
                status="apply_failed",
                written_paths=written,
                test_exit_code=exit_code,
                test_output=output,
                backup_path=str(backup_dir),
                message="post-apply verification failed; changes retained, restore available",
            )
            self.store.record_apply_result(run_id, result)
            self.store.transition(run_id, RunPhase.APPLY_FAILED)
            return result

        result = ApplyResult(
            status="applied",
            written_paths=written,
            test_exit_code=exit_code,
            test_output=output,
            backup_path=str(backup_dir),
            message="applied successfully",
        )
        self.store.complete_apply(run_id, result)
        return result

    def restore(self, run_id: str) -> ApplyResult:
        snapshot = self.store.load(run_id)
        if snapshot.apply_result is not None and snapshot.apply_result.status == "restored":
            return snapshot.apply_result
        if (
            snapshot.phase is not RunPhase.APPLY_FAILED
            or snapshot.apply_result is None
            or snapshot.apply_result.backup_path is None
        ):
            raise ValueError("no backup available to restore for this run")

        backup_dir = Path(snapshot.apply_result.backup_path)
        manifest_path = backup_dir / _MANIFEST_NAME
        if not manifest_path.exists():
            raise ValueError(
                f"no restorable backup manifest found for this run: {manifest_path}",
            )
        manifest: dict[str, dict[str, Any]] = json.loads(
            manifest_path.read_text(encoding="utf-8"),
        )
        source = Path(snapshot.project_path).resolve()

        conflicts = [
            relative
            for relative, info in manifest.items()
            if file_hash(safe_target(source, relative)) != info.get("applied_hash")
        ]
        if conflicts:
            result = ApplyResult(
                status="conflict",
                backup_path=str(backup_dir),
                message=f"source edited after apply, cannot restore: {', '.join(sorted(conflicts))}",
            )
            self.store.record_apply_result(run_id, result)
            return result

        for relative, info in manifest.items():
            target = safe_target(source, relative)
            if info["existed"]:
                self._atomic_write(run_id, target, (backup_dir / relative).read_bytes())
            elif target.exists():
                target.unlink()

        result = ApplyResult(
            status="restored", backup_path=str(backup_dir), message="source restored from backup",
        )
        self.store.record_apply_result(run_id, result)
        self.store.transition(run_id, RunPhase.APPROVED)
        return result

    @staticmethod
    def _detect_conflicts(snapshot: RunSnapshot, source: Path) -> list[str]:
        current = snapshot_project(source)
        return [
            path for path in snapshot.changed_paths
            if current.get(path) != snapshot.source_hashes.get(path)
        ]

    @staticmethod
    def _atomic_write(run_id: str, target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".nova-{run_id}.{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(target)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _rollback(
        source: Path, backup_dir: Path, manifest: dict[str, dict[str, Any]], written: list[str],
    ) -> None:
        for relative in written:
            target = safe_target(source, relative)
            info = manifest.get(relative, {})
            backup_file = backup_dir / relative
            if info.get("existed") and backup_file.exists():
                shutil.copy2(backup_file, target)
            elif not info.get("existed") and target.exists():
                target.unlink()

    def _backup_dir(self, run_id: str) -> Path:
        return self.store.root / "_backups" / run_id
