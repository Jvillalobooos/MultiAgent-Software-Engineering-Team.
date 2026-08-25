import re
import shutil
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
