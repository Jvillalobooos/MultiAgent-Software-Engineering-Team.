"""End-to-end proof: a chat-launched run edits an isolated workspace copy and,
once approved, Apply writes the same change back into the real source project
with real backup and real post-apply pytest verification."""

from __future__ import annotations

import difflib
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engineering_team.apply_service import ApplyService, PytestVerificationRunner
from engineering_team.config import Settings
from engineering_team.run_api import RunExecutor, RunManager, create_runs_router
from engineering_team.runs import RunSnapshot, RunStore


def copy_calculator_demo(destination: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "demo-projects" / "calculadora-qa-demo"
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    return destination


def calculator_change_executor(
    snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    target = Path(snapshot.workspace_path) / "calculadora" / "__init__.py"
    original = target.read_text(encoding="utf-8")
    updated = original + "\nVERSION = 2\n"
    target.write_text(updated, encoding="utf-8")
    emit({
        "name": "Developer write", "agent": "developer", "type": "tool",
        "level": "info", "status_message": "calculadora/__init__.py updated",
        "metadata": {"status": "SUCCESS"}, "iteration": 0, "at": 1,
    })
    return approved_state_with_applied_diff(
        snapshot.run_id, "calculadora/__init__.py", original, updated,
    )


def approved_state_with_applied_diff(
    run_id: str, path: str, before: str, after: str,
) -> dict[str, Any]:
    diff = "\n".join(difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="",
    ))
    return {
        "run_id": run_id, "iteration": 0, "final_status": "APPROVED",
        "route_history": ["Product", "Architecture", "Developer", "Security",
                          "Testing", "Reviewer", "FinalReport"],
        "implementation": {
            "action_mode": "APPLIED", "changed_files": [path], "diff": diff,
            "evidence": [path], "validation_result": "workspace tests passed",
            "security_surface_changed": False, "file_contents": {path: after},
        },
        "review": {
            "status": "APPROVED", "score": 100,
            "subscores": {"requirements": 100, "architecture": 100, "security": 100,
                          "testing": 100, "implementation": 100, "rag_grounding": 100},
            "problems": [], "reason": "validated evidence satisfies acceptance checks",
            "remediation_category": None, "return_to": None, "confidence": 1,
            "evidence_references": [path],
        },
        "model_usage": [], "rag_evidence": [],
        "tool_results": [
            {
                "tool_name": "update_file", "status": "SUCCESS", "duration_ms": 1,
                "allowed_role": "Developer", "input_summary": "safe",
                "output_summary": path, "error": None,
            },
            {
                "tool_name": "run_tests", "status": "SUCCESS", "duration_ms": 1,
                "allowed_role": "Testing", "input_summary": "safe",
                "output_summary": "21 passed", "error": None,
            },
        ],
        "errors": [],
    }


def chat_app_client(records: Path, executor: RunExecutor) -> TestClient:
    settings = Settings(workspace_root=str(records / "workspaces"))
    store = RunStore(records)
    manager = RunManager(settings=settings, store=store, executor=executor)
    apply_service = ApplyService(
        store, verification=PytestVerificationRunner(paths=["tests/test_operaciones.py"]),
    )
    app = FastAPI()
    app.include_router(create_runs_router(manager, apply_service=apply_service))
    return TestClient(app)


def wait_for_phase(client: TestClient, run_id: str, phase: str) -> dict[str, Any]:
    for _ in range(200):
        payload = client.get(f"/api/runs/{run_id}").json()
        if payload["phase"] == phase:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {phase}: last phase {payload['phase']}")


def test_message_runs_in_copy_then_applies_to_source(tmp_path: Path) -> None:
    source = copy_calculator_demo(tmp_path / "calculator")
    client = chat_app_client(tmp_path / "runs", executor=calculator_change_executor)
    created = client.post("/api/runs", json={
        "projectPath": str(source),
        "message": "Add a public VERSION constant with value 2",
    })
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    wait_for_phase(client, run_id, "approved")
    assert "VERSION = 2" not in (source / "calculadora" / "__init__.py").read_text()

    applied = client.post(f"/api/runs/{run_id}/apply", json={
        "projectPath": str(source.resolve()), "confirmed": True,
    })
    assert applied.json()["status"] == "applied"
    assert "VERSION = 2" in (source / "calculadora" / "__init__.py").read_text()
    assert applied.json()["test_exit_code"] == 0
