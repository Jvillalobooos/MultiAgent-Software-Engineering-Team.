"""Reset a demo project back to its initial git commit.

Used to restore a project under ``demo-projects/`` to its pristine baseline
between ``run-project`` demo runs, without having to remember the initial
commit hash by hand.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def reset_project(project_path: str | Path) -> dict[str, Any]:
    """Hard-reset ``project_path``'s own git repository to its root commit.

    Refuses to run unless ``project_path`` is itself a git repository — this
    only ever touches the target project's history, never the repository
    this module lives in.
    """
    root = Path(project_path).resolve()
    this_repo_root = Path(__file__).resolve().parents[2]
    if root == this_repo_root:
        raise ValueError("refusing to reset this project's own repository")
    if not (root / ".git").is_dir():
        raise ValueError(f"{root} is not a git repository (no .git directory)")

    root_commit = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()[-1]
    subprocess.run(["git", "-C", str(root), "reset", "--hard", root_commit], check=True)
    clean = subprocess.run(
        ["git", "-C", str(root), "clean", "-fd"],
        capture_output=True, text=True, check=True,
    )
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--short"],
        capture_output=True, text=True, check=True,
    )
    return {
        "project_path": str(root),
        "reset_to": root_commit,
        "removed_untracked": [line for line in clean.stdout.splitlines() if line],
        "status_after": status.stdout,
    }
