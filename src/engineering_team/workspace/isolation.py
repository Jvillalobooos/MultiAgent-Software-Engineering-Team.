import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .paths import resolve_inside


def create_run_copy(run_id: str, source: str | Path, workspace_root: str | Path) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("invalid run_id")
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ValueError("source workspace does not exist")
    root = Path(workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = resolve_inside(root, run_id)
    if destination.exists():
        raise FileExistsError(f"run workspace already exists: {run_id}")
    def ignored(current: str, names: list[str]) -> set[str]:
        relative = Path(current).resolve().relative_to(source_path).as_posix()
        blocked = {".venv", ".git", "__pycache__"}
        if relative in {"workspace", "rag"}:
            blocked.add("runs" if relative == "workspace" else "chroma")
        return blocked.intersection(names)

    shutil.copytree(source_path, destination, ignore=ignored)
    return destination


@dataclass
class WorkspaceFingerprint:
    workspace_path: Path
    source_path: Path
    file_hashes: dict[str, str] = field(default_factory=dict)


_EXCLUDED_DIR_NAMES = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}


def _is_excluded(relative_parts: tuple[str, ...], name: str) -> bool:
    if name in _EXCLUDED_DIR_NAMES:
        return True
    return name == ".env" or name.startswith(".env.")


def create_api_workspace(
    run_id: str, source: str | Path, workspace_root: str | Path
) -> WorkspaceFingerprint:
    """Copy `source` into an isolated, hash-fingerprinted workspace for the API executor.

    Excludes .git/.venv/__pycache__/node_modules/caches, .env*, and any
    symlink (whether or not it escapes `source`) — a future FastAPI layer
    runs the graph against the returned workspace_path, never `source`.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("invalid run_id")
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ValueError("source project does not exist")
    root = Path(workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = resolve_inside(root, run_id)
    if destination.exists():
        raise FileExistsError(f"run workspace already exists: {run_id}")

    file_hashes: dict[str, str] = {}
    for current_dir, dir_names, file_names in os.walk(source_path, followlinks=False):
        current = Path(current_dir)
        relative_dir = current.relative_to(source_path)
        dir_names[:] = [name for name in dir_names if not _is_excluded(relative_dir.parts, name)]
        target_dir = destination / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in file_names:
            source_file = current / name
            if source_file.is_symlink() or _is_excluded(relative_dir.parts, name):
                continue
            relative_file = (relative_dir / name).as_posix()
            data = source_file.read_bytes()
            (destination / relative_dir / name).write_bytes(data)
            file_hashes[relative_file] = hashlib.sha256(data).hexdigest()

    return WorkspaceFingerprint(
        workspace_path=destination, source_path=source_path, file_hashes=file_hashes,
    )
