"""Reproducible demo fixtures; never changes the multi-agent system's history."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent / "banca-demo"
BASELINE = HERE / "baseline.json"
SKIP = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", ".git"}


def make_manifest(project: Path) -> dict:
    files = {}
    for path in sorted(project.rglob("*")):
        rel = path.relative_to(project)
        if any(part in SKIP or part.endswith(".egg-info") for part in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed: {rel}")
        if not path.is_file() or path.suffix in {".db", ".pyc"}:
            continue
        content = path.read_text(encoding="utf-8")
        files[rel.as_posix()] = {"content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()}
    return {"version": 1, "files": files}


def restore(project: Path, manifest: dict) -> None:
    marker = project / ".banca-demo"
    if project.is_symlink() or project.name != "banca-demo" or not marker.is_file() or marker.is_symlink():
        raise ValueError("refusing reset outside a marked banca-demo directory")
    if marker.read_text() != "banca-demo-v1\n" or manifest.get("version") != 1:
        raise ValueError("invalid demo marker or baseline version")
    files = manifest.get("files", {})
    if ".banca-demo" not in files:
        raise ValueError("baseline marker missing")
    for name, entry in files.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("unsafe baseline path")
        if hashlib.sha256(entry["content"].encode()).hexdigest() != entry["sha256"]:
            raise ValueError(f"baseline checksum mismatch: {name}")
    # All validation precedes deletion. Unlink symlinks without following them.
    for path in project.iterdir():
        if path.is_symlink() or path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
    for name, entry in files.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(entry["content"], encoding="utf-8")
        if path.suffix == ".sh":
            path.chmod(0o755)


def read_cases(readme: Path) -> list[dict]:
    sections = re.split(r"^### Caso (\d+) — (.+)$", readme.read_text(), flags=re.MULTILINE)
    cases = []
    for offset in range(1, len(sections), 3):
        number, title, body = sections[offset:offset + 3]
        blocks = re.findall(r"```\s*\n(.*?)```", body, flags=re.DOTALL)
        cases.append({"id": int(number), "title": title, "message": blocks[0].strip(),
                      "testSpec": blocks[1].strip() if len(blocks) > 1 else None})
    if [case["id"] for case in cases] != list(range(1, 8)):
        raise ValueError("README must contain exactly seven numbered cases")
    # Case 7 is followed by shell usage blocks; only Test specification is a test.
    for case in cases[5:]:
        case["testSpec"] = None
    return cases


INFRASTRUCTURE_MARKERS = (
    "AGENT_TIMEOUT", "ReadTimeout", "LLM_AVAILABILITY_ERROR",
    "CLOUD_FALLBACK_UNAVAILABLE", "MCP_ERROR", "WORKFLOW_ERROR",
)


def outcome(snapshot: dict, *, negative: bool, expected_finding: str | None = None) -> str:
    if not snapshot.get("authorize_writes") or not snapshot.get("trace_id"):
        return "retry"
    review = (snapshot.get("report") or {}).get("review", {})
    if "sensitive content is not allowed" in review.get("reason", ""):
        return "security_stop"
    # A run that died on infrastructure also lands on HUMAN_REVIEW_REQUIRED with a zero
    # security subscore, because nothing ran -- not because anything was found. Those
    # must stay retryable; only a real, evidenced finding counts as the expected reject.
    reason = str(review.get("reason", ""))
    if any(marker in reason for marker in INFRASTRUCTURE_MARKERS):
        return "retry"
    security_failed = (review.get("status") in {"REJECTED", "HUMAN_REVIEW_REQUIRED"}
                       and review.get("subscores", {}).get("security", 100) == 0
                       and bool(review.get("problems")))
    if security_failed:
        if not negative:
            return "security_stop"
        expected = (expected_finding,) if expected_finding else (
            "password reset tokens must expire", "reset token never expires",
            "resource access must be ownership-authorized",
        )
        problems = [" ".join(str(problem).lower().split()) for problem in review["problems"]]
        matched = any(finding in problem for finding in expected for problem in problems)
        return "rejected" if matched and snapshot["phase"] == "review_required" else "retry"
    result = snapshot.get("apply_result") or {}
    if (not negative and snapshot["phase"] == "applied" and review.get("status") == "APPROVED"
            and result.get("status") == "applied" and result.get("test_exit_code") == 0
            and snapshot.get("changed_paths")):
        return "applied"
    return "retry"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["restore", "check"])
    args = parser.parse_args()
    manifest = json.loads(BASELINE.read_text())
    if args.action == "restore":
        import urllib.request
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/api/runs", timeout=3) as response:
                runs = json.load(response)
            runs = runs.get("runs", []) if isinstance(runs, dict) else runs
            if any(run.get("project_path") == str(PROJECT) and run.get("phase") in
                   {"queued", "preparing", "running", "applying"} for run in runs):
                raise SystemExit("An active run uses banca-demo. Wait before resetting.")
        except OSError:
            pass  # Offline reset is allowed; stop any bank API process yourself.
        restore(PROJECT, manifest)
    if make_manifest(PROJECT) != manifest:
        raise SystemExit("Project differs from baseline. Run restore.sh before a new demo.")
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "--disable-warnings"], cwd=PROJECT, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("Baseline verified; multi-agent run history and demo evidence preserved.")


if __name__ == "__main__":
    main()
