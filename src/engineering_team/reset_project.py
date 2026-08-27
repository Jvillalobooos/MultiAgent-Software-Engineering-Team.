"""Reset a demo project back to its original baseline.

Used to restore a project under ``demo-projects/`` between ``run-project``
demo runs. Handles two shapes:

- **Independent repo** (``<project>/.git`` exists): hard-reset that repo to
  its own root commit and remove untracked files.
- **Tracked subtree** (no ``.git`` of its own, e.g. it was folded into this
  repo's history): restore the folder's contents to the earliest commit
  that added it, remove any files added since, and commit the restoration.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def reset_project(project_path: str | Path) -> dict[str, Any]:
    """Reset ``project_path`` to its baseline, refusing to touch this repo itself."""
    root = Path(project_path).resolve()
    this_repo_root = Path(__file__).resolve().parents[2]
    if root == this_repo_root:
        raise ValueError("refusing to reset this project's own repository")

    if (root / ".git").is_dir():
        return _reset_independent_repo(root)
    return _reset_tracked_subtree(root, this_repo_root)


def _reset_independent_repo(root: Path) -> dict[str, Any]:
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
        "mode": "independent-repo",
        "reset_to": root_commit,
        "removed_untracked": [line for line in clean.stdout.splitlines() if line],
        "status_after": status.stdout,
    }


def _reset_tracked_subtree(root: Path, repo_root: Path) -> dict[str, Any]:
    relative = root.relative_to(repo_root).as_posix()
    history = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--reverse", "--format=%H", "--", relative],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    if not history:
        raise ValueError(f"{root} is not a git repository and is not tracked in {repo_root}")
    baseline_commit = history[0]

    subprocess.run(
        ["git", "-C", str(repo_root), "checkout", baseline_commit, "--", relative],
        check=True,
    )

    # Tracked files added since the baseline (e.g. someone `git add`ed a
    # run-project result before calling reset).
    baseline_files = set(subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "--name-only", baseline_commit, "--", relative],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines())
    current_files = set(subprocess.run(
        ["git", "-C", str(repo_root), "ls-files", "--", relative],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines())
    tracked_extra = sorted(current_files - baseline_files)
    if tracked_extra:
        subprocess.run(["git", "-C", str(repo_root), "rm", "-q", "--", *tracked_extra], check=True)

    # Untracked files added since the baseline: run-project's MCP writes never
    # `git add`, so a freshly-created file (e.g. a new test) sits untracked —
    # this is the common case after a real --authorize-writes run.
    clean = subprocess.run(
        ["git", "-C", str(repo_root), "clean", "-fd", "--", relative],
        capture_output=True, text=True, check=True,
    )
    untracked_extra = [line.removeprefix("Removing ") for line in clean.stdout.splitlines() if line]
    extra = tracked_extra + untracked_extra

    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--short", "--", relative],
        capture_output=True, text=True, check=True,
    ).stdout
    if status.strip():
        subprocess.run(
            [
                "git", "-C", str(repo_root), "commit",
                "-m", f"Restore {relative} to its baseline ({baseline_commit[:7]})",
                "--", relative,
            ],
            check=True,
        )
    return {
        "project_path": str(root),
        "mode": "tracked-subtree",
        "reset_to": baseline_commit,
        "removed_untracked": extra,
        "status_after": status,
    }
