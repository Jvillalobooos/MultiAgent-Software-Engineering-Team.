from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import engineering_team.run_api as run_api_module
from engineering_team.apply_service import ApplyService, file_hash, snapshot_project
from engineering_team.config import Settings
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.langfuse import TraceSession
from engineering_team.run_api import RunManager, create_runs_router
from engineering_team.run_events import (
    EventForwardingTrace,
    final_report_from_state,
    run_event_from_trace,
)
from engineering_team.runs import ApplyResult, RunPhase, RunSnapshot, RunStore


def _completed_state(run_id: str = "run-1") -> dict[str, Any]:
    return {
        "run_id": run_id,
        "iteration": 1,
        "final_status": "APPROVED",
        "route_history": [
            "Product", "Architecture", "Developer", "Security", "Testing",
            "Reviewer", "FinalReport",
        ],
        "implementation": {
            "action_mode": "PROPOSED",
            "changed_files": ["app/service.py"],
            "diff": "--- a/app/service.py\n+++ b/app/service.py\n@@ -1 +1 @@\n-old\n+new\n",
        },
        "review": {
            "status": "APPROVED",
            "score": 91,
            "subscores": {
                "requirements": 92, "architecture": 90, "security": 89,
                "testing": 91, "implementation": 93, "rag_grounding": 88,
            },
            "problems": [],
            "reason": "All acceptance criteria passed.",
        },
        "model_usage": [{
            "agent": "Product", "provider": "ollama", "actual_model": "qwen3.5:4b",
            "requested_model": "qwen3.5:4b", "latency_ms": 120,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }],
        "rag_evidence": [{
            "source": "docs/spec.md", "section": "Limits", "score": 0.87,
            "fragment": "Return five records.", "domain": "requirements",
        }],
        "tool_results": [{
            "tool_name": "run_tests", "status": "SUCCESS", "duration_ms": 42,
            "allowed_role": "Testing", "output_summary": "12 passed", "error": None,
        }],
        "errors": [],
    }


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("value = 1\n", encoding="utf-8")
    return source


def _settings(tmp_path: Path) -> Settings:
    return Settings(workspace_root=str(tmp_path / "workspaces"))


def _manager(
    tmp_path: Path,
    executor: Callable[[RunSnapshot, Callable[[dict[str, Any]], None]], dict[str, Any]],
) -> RunManager:
    return RunManager(
        settings=_settings(tmp_path),
        store=RunStore(tmp_path / "records"),
        executor=executor,
    )


def _client(manager: RunManager, apply_service: ApplyService | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(create_runs_router(manager, apply_service=apply_service))
    return TestClient(app)


class _PassingVerification:
    def run(self, project: Path) -> tuple[int, str]:
        return 0, "1 passed"


def _approved_run_client(
    tmp_path: Path, source: Path, workspace: Path, changed_paths: list[str],
) -> tuple[TestClient, RunStore, str]:
    store = RunStore(tmp_path / "records")
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes=snapshot_project(source),
        changed_paths=changed_paths, report={"review": {"status": "APPROVED"}},
    ))
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )
    client = _client(manager, ApplyService(store, verification=_PassingVerification()))
    return client, store, str(source.resolve())


def _wait_for_phase(client: TestClient, run_id: str, phase: str) -> dict[str, Any]:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        if response.status_code == 200 and response.json()["phase"] == phase:
            return response.json()
        time.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {phase}")


def _event(name: str, *, agent: str = "product") -> dict[str, Any]:
    return {
        "name": name, "agent": agent, "type": "model", "level": "info",
        "status_message": name, "metadata": {}, "iteration": 0, "at": 1,
    }


def test_trace_event_matches_the_public_run_event_contract() -> None:
    event = run_event_from_trace(
        run_id="run-1", sequence=3,
        trace_event={
            "name": "model call", "type": "generation", "level": None,
            "status_message": "completed",
            "metadata": {"agent": "Product", "iteration": 2, "provider": "ollama"},
            "input": {"task": "specify"}, "output": {"ok": True}, "model": "qwen3.5:4b",
            "usage_details": {"input_tokens": 10, "output_tokens": 20, "latency_ms": 120},
        }, observed_at=1234,
    )

    assert event == {
        "id": "run-1-3", "name": "model call", "type": "model", "level": "info",
        "status_message": "completed",
        "metadata": {"agent": "Product", "iteration": 2, "provider": "ollama"},
        "model": "qwen3.5:4b", "input": '{"task":"specify"}', "output": '{"ok":true}',
        "usage_details": {"input_tokens": 10, "output_tokens": 20, "latency_ms": 120},
        "agent": "product", "iteration": 2, "at": 1234,
    }


def test_final_report_distinguishes_proposals_from_workspace_writes() -> None:
    report = final_report_from_state(_completed_state())

    assert set(report) == {
        "route_history", "model_usage", "changed_files", "applied_diff",
        "workspace_changed", "actual_changed_paths", "source_applied", "review",
        "errors", "rag_evidence", "tool_results",
    }
    assert report["review"]["status"] == "APPROVED"
    assert report["changed_files"][0]["additions"] == 1
    assert report["changed_files"][0]["deletions"] == 1
    assert report["workspace_changed"] is False
    assert report["source_applied"] is False
    assert report["model_usage"] == [{
        "agent": "product", "model": "qwen3.5:4b", "provider": "local", "calls": 1,
        "input_tokens": 10, "output_tokens": 20, "avg_latency_ms": 120,
    }]
    assert report["tool_results"] == [{
        "name": "run_tests", "status": "SUCCESS", "duration_ms": 42,
        "agent": "testing", "detail": "12 passed",
    }]


def test_final_report_marks_successful_write_evidence_as_workspace_change() -> None:
    state = _completed_state()
    state["implementation"]["action_mode"] = "APPLIED"
    state["tool_results"].append({
        "tool_name": "update_file", "status": "SUCCESS", "duration_ms": 8,
        "allowed_role": "Developer", "output_summary": "app/service.py", "error": None,
    })

    report = final_report_from_state(state)

    assert report["applied_diff"] is True
    assert report["workspace_changed"] is True
    assert report["source_applied"] is False
    assert report["tool_results"][-1]["name"] == "update_file"


def test_recovered_cloud_fallback_stays_a_warning_and_run_still_approves() -> None:
    state = _completed_state()
    state["model_usage"] = [
        {
            "agent": "Product", "provider": "google", "actual_model": None,
            "requested_model": "gemini-3.7-flash", "latency_ms": 80,
            "usage": None, "error": "CLOUD_FALLBACK_UNAVAILABLE: provider_unavailable (HTTP 503)",
            "http_status": 503, "error_category": "provider_unavailable", "retryable": True,
        },
        {
            "agent": "Product", "provider": "ollama", "actual_model": "qwen3.5:4b",
            "requested_model": "qwen3.5:4b", "latency_ms": 120,
            "usage": {"input_tokens": 10, "output_tokens": 20},
        },
    ]

    failed_event = run_event_from_trace(
        run_id="run-1", sequence=1,
        trace_event={
            "name": "product cloud primary", "type": "generation", "level": "ERROR",
            "status_message": "CLOUD_FALLBACK_UNAVAILABLE: provider_unavailable (HTTP 503)",
            "metadata": {
                "agent": "Product", "http_status": 503,
                "error_category": "provider_unavailable", "retryable": "true",
            },
        },
    )
    assert failed_event["level"] == "error"
    assert failed_event["type"] == "error"
    assert failed_event["metadata"]["error_category"] == "provider_unavailable"

    report = final_report_from_state(state)

    assert report["review"]["status"] == "APPROVED"
    local_entry = next(
        item for item in report["model_usage"] if item["provider"] == "local"
    )
    cloud_entry = next(
        item for item in report["model_usage"] if item["provider"] == "cloud"
    )
    assert local_entry["fallback_succeeded"] is True
    assert cloud_entry["error_category"] == "provider_unavailable"
    assert cloud_entry["http_status"] == 503
    assert cloud_entry["retryable"] is True
    assert "fallback_succeeded" not in cloud_entry


def test_post_creates_independent_persisted_runs(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def executor(
        snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        emit(_event(snapshot.message))
        return _completed_state(snapshot.run_id)

    manager = _manager(tmp_path, executor)
    client = _client(manager)
    first = client.post("/api/runs", json={"projectPath": str(source), "message": "alpha"})
    second = client.post("/api/runs", json={"projectPath": str(source), "message": "beta"})

    assert first.status_code == second.status_code == 202
    assert first.json()["run_id"] != second.json()["run_id"]
    first_id, second_id = first.json()["run_id"], second.json()["run_id"]
    assert _wait_for_phase(client, first_id, "approved")["message"] == "alpha"
    assert _wait_for_phase(client, second_id, "approved")["message"] == "beta"
    assert {item["run_id"] for item in client.get("/api/runs").json()} == {first_id, second_id}


def test_launch_defaults_to_dry_run_in_public_snapshot(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manager = _manager(tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id))
    client = _client(manager)

    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "keep it safe"},
    ).json()["run_id"]

    snapshot = _wait_for_phase(client, run_id, "approved")

    assert snapshot["test_spec"] is None
    assert snapshot["authorize_writes"] is False


def test_launch_persists_test_spec_and_explicit_write_authorization(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manager = _manager(tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id))
    client = _client(manager)

    run_id = client.post("/api/runs", json={
        "projectPath": str(source),
        "message": "fix the calculation",
        "testSpec": "tests/test_mediana_par.py must pass",
        "authorizeWrites": True,
    }).json()["run_id"]

    snapshot = _wait_for_phase(client, run_id, "approved")

    assert snapshot["test_spec"] == "tests/test_mediana_par.py must pass"
    assert snapshot["authorize_writes"] is True


def test_real_executor_forwards_persisted_test_spec_and_write_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    captured: dict[str, Any] = {}

    def fake_execute_on_project(
        _settings: Settings,
        *,
        project_path: str,
        specification: str,
        test_specification: str | None = None,
        authorize_writes: bool = False,
        run_id: str | None = None,
        event_observer: Callable[[dict[str, Any]], None] | None = None,
        on_trace_started: Callable[[str], None] | None = None,
    ) -> tuple[dict[str, Any], None, float, bool]:
        captured.update({
            "project_path": project_path,
            "specification": specification,
            "test_specification": test_specification,
            "authorize_writes": authorize_writes,
            "run_id": run_id,
        })
        if on_trace_started is not None:
            on_trace_started("trace-abc123")
        return _completed_state(str(run_id)), None, 0.0, False

    monkeypatch.setattr(run_api_module, "execute_on_project", fake_execute_on_project)
    manager = RunManager(settings=_settings(tmp_path), store=RunStore(tmp_path / "records"))
    client = _client(manager)

    run_id = client.post("/api/runs", json={
        "projectPath": str(source),
        "message": "fix the calculation",
        "testSpec": "tests/test_mediana_par.py must pass",
        "authorizeWrites": False,
    }).json()["run_id"]

    snapshot = _wait_for_phase(client, run_id, "approved")

    assert captured == {
        "project_path": str((tmp_path / "workspaces" / run_id).resolve()),
        "specification": "fix the calculation",
        "test_specification": "tests/test_mediana_par.py must pass",
        "authorize_writes": False,
        "run_id": run_id,
    }
    # The trace id the executor reported is persisted and publicly readable, so the
    # UI can cite the real trace instead of a positional run label.
    assert snapshot["trace_id"] == "trace-abc123"
    assert client.get("/api/runs").json()[0]["trace_id"] == "trace-abc123"


def test_completed_run_persists_changed_paths_from_successful_writes(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def executor(
        snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        state = _completed_state(snapshot.run_id)
        state["implementation"]["action_mode"] = "APPLIED"
        state["tool_results"].append({
            "tool_name": "update_file", "status": "SUCCESS", "duration_ms": 8,
            "allowed_role": "Developer", "output_summary": "app/service.py", "error": None,
        })
        return state

    manager = _manager(tmp_path, executor)
    client = _client(manager)
    response = client.post("/api/runs", json={"projectPath": str(source), "message": "alpha"})
    run_id = response.json()["run_id"]

    body = _wait_for_phase(client, run_id, "approved")

    assert body["changed_paths"] == ["app/service.py"]


def test_default_dry_run_never_applies_workspace_change_to_selected_source(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (source / "test_app.py").write_text(
        "from app import value\n\ndef test_value():\n    assert value == 2\n", encoding="utf-8"
    )

    def executor(snapshot: RunSnapshot, _emit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        (Path(snapshot.workspace_path) / "app.py").write_text("value = 2\n", encoding="utf-8")
        state = _completed_state(snapshot.run_id)
        state["implementation"]["action_mode"] = "APPLIED"
        state["tool_results"].append({
            "tool_name": "update_file", "status": "SUCCESS", "duration_ms": 1,
            "allowed_role": "Developer", "output_summary": "app.py", "error": None,
        })
        return state

    client = _client(_manager(tmp_path, executor))
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "write value"},
    ).json()["run_id"]

    snapshot = _wait_for_phase(client, run_id, "approved")

    assert (source / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert snapshot["report"]["source_applied"] is False
    assert snapshot["authorize_writes"] is False


def test_approved_workspace_change_is_applied_to_selected_source(tmp_path: Path) -> None:
    source = _source(tmp_path)
    (source / "test_app.py").write_text(
        "from app import value\n\ndef test_value():\n    assert value == 2\n", encoding="utf-8"
    )

    def executor(snapshot: RunSnapshot, _emit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        (Path(snapshot.workspace_path) / "app.py").write_text("value = 2\n", encoding="utf-8")
        state = _completed_state(snapshot.run_id)
        state["implementation"]["action_mode"] = "APPLIED"
        state["tool_results"].append({
            "tool_name": "update_file", "status": "SUCCESS", "duration_ms": 1,
            "allowed_role": "Developer", "output_summary": "app.py", "error": None,
        })
        return state

    client = _client(_manager(tmp_path, executor))
    run_id = client.post(
        "/api/runs", json={
            "projectPath": str(source), "message": "write value", "authorizeWrites": True,
        }
    ).json()["run_id"]

    snapshot = _wait_for_phase(client, run_id, "applied")
    assert (source / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    assert snapshot["report"]["source_applied"] is True


@pytest.mark.parametrize("actual_diff,expected", [
    ("", []),
    ("--- a/app/service.py\n+++ b/app/service.py\n@@ -1 +1 @@\n-old\n+new\n", ["app/service.py"]),
])
def test_real_diff_omits_unchanged_writes_but_preserves_the_tool_audit(actual_diff, expected):
    state = _completed_state()
    for path in ["app/service.py", "app/unchanged.py"]:
        state["tool_results"].append({
            "tool_name": "update_file", "status": "SUCCESS", "duration_ms": 1,
            "allowed_role": "Developer", "output_summary": path})
    state["tool_results"].append({
        "tool_name": "get_diff", "status": "SUCCESS", "duration_ms": 1,
        "allowed_role": "Developer", "output_summary": actual_diff})
    report = final_report_from_state(state)
    assert [item["path"] for item in report["changed_files"]] == expected
    assert report["actual_changed_paths"] == ["app/service.py", "app/unchanged.py"]
    assert sum(item["name"] == "update_file" for item in report["tool_results"]) == 2


def test_changed_paths_ignore_model_claimed_diff_paths_never_actually_written(
    tmp_path: Path,
) -> None:
    """The model's diff can claim any path -- only real tool writes may be applied."""
    source = _source(tmp_path)

    def executor(
        snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        state = _completed_state(snapshot.run_id)
        # Model diff claims a path, but no create_file/update_file tool call for it
        # actually succeeded -- this must NOT end up in changed_paths.
        state["implementation"]["changed_files"] = ["app/never_written.py"]
        state["implementation"]["diff"] = (
            "--- a/app/never_written.py\n+++ b/app/never_written.py\n"
            "@@ -1 +1 @@\n-old\n+new\n"
        )
        return state

    manager = _manager(tmp_path, executor)
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "alpha"},
    ).json()["run_id"]

    body = _wait_for_phase(client, run_id, "approved")

    assert body["changed_paths"] == []
    assert body["report"]["changed_files"][0]["path"] == "app/never_written.py"


def test_changed_paths_include_tool_written_path_even_when_absent_from_model_diff(
    tmp_path: Path,
) -> None:
    """A path a tool call actually wrote must count even if the model's diff omits it."""
    source = _source(tmp_path)

    def executor(
        snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        state = _completed_state(snapshot.run_id)
        state["implementation"]["changed_files"] = []
        state["implementation"]["diff"] = ""
        state["tool_results"].append({
            "tool_name": "create_file", "status": "SUCCESS", "duration_ms": 5,
            "allowed_role": "Developer", "output_summary": "app/really_written.py",
            "error": None,
        })
        return state

    manager = _manager(tmp_path, executor)
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "alpha"},
    ).json()["run_id"]

    body = _wait_for_phase(client, run_id, "approved")

    assert body["changed_paths"] == ["app/really_written.py"]


def test_completed_run_leaves_changed_paths_empty_without_workspace_write(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manager = _manager(tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id))
    client = _client(manager)
    response = client.post("/api/runs", json={"projectPath": str(source), "message": "alpha"})
    run_id = response.json()["run_id"]

    body = _wait_for_phase(client, run_id, "approved")

    assert body["changed_paths"] == []


def test_completed_snapshot_survives_manager_restart(tmp_path: Path) -> None:
    source = _source(tmp_path)
    records = tmp_path / "records"
    first_manager = RunManager(
        settings=_settings(tmp_path), store=RunStore(records),
        executor=lambda snapshot, _emit: _completed_state(snapshot.run_id),
    )
    first_client = _client(first_manager)
    run_id = first_client.post(
        "/api/runs", json={"projectPath": str(source), "message": "persist me"},
    ).json()["run_id"]
    _wait_for_phase(first_client, run_id, "approved")

    restarted = RunManager(
        settings=_settings(tmp_path), store=RunStore(records),
        executor=lambda *_: _completed_state(),
    )
    response = _client(restarted).get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["message"] == "persist me"
    assert response.json()["report"]["review"]["status"] == "APPROVED"


@pytest.mark.parametrize(
    "interrupted_phase",
    [RunPhase.QUEUED, RunPhase.PREPARING, RunPhase.RUNNING],
)
def test_manager_restart_reconciles_interrupted_run_to_queryable_failure(
    tmp_path: Path, interrupted_phase: RunPhase,
) -> None:
    records = tmp_path / "records"
    store = RunStore(records)
    store.create(RunSnapshot(
        run_id=f"run-{interrupted_phase.value}",
        project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "workspace"),
        message="resume safely",
        phase=interrupted_phase,
        source_hashes={},
    ))

    manager = RunManager(
        settings=_settings(tmp_path),
        store=RunStore(records),
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("must not resume")),
    )
    run_id = f"run-{interrupted_phase.value}"
    response = _client(manager).get(f"/api/runs/{run_id}")

    assert response.status_code == 200
    assert response.json()["phase"] == "failed"
    assert response.json()["report"]["review"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert len(response.json()["events"]) == 1
    assert RunStore(records).load(run_id).phase is RunPhase.FAILED


def test_manager_restart_reconciles_stranded_applying_run_to_apply_failed(
    tmp_path: Path,
) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    records = tmp_path / "records"
    store = RunStore(records)
    store.create(RunSnapshot(
        run_id="run-stuck", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes=snapshot_project(source),
        changed_paths=["app.py"], report={"review": {"status": "APPROVED"}},
    ))
    store.transition("run-stuck", RunPhase.APPLYING)

    manager = RunManager(
        settings=_settings(tmp_path),
        store=RunStore(records),
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("must not resume")),
    )
    client = _client(manager)

    response = client.get("/api/runs/run-stuck")

    assert response.status_code == 200
    assert response.json()["phase"] == "apply_failed"
    assert response.json()["apply_result"]["status"] == "apply_failed"
    assert response.json()["apply_result"]["backup_path"] is None
    assert RunStore(records).load("run-stuck").phase is RunPhase.APPLY_FAILED


def test_manager_restart_reconciles_stranded_applying_run_with_valid_backup_and_restores(
    tmp_path: Path,
) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("new\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    records = tmp_path / "records"
    store = RunStore(records)
    store.create(RunSnapshot(
        run_id="run-stuck", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes=snapshot_project(source),
        changed_paths=["app.py"], report={"review": {"status": "APPROVED"}},
    ))
    store.transition("run-stuck", RunPhase.APPLYING)
    backup_dir = records / "_backups" / "run-stuck"
    backup_dir.mkdir(parents=True)
    (backup_dir / "app.py").write_text("old\n", encoding="utf-8")
    (backup_dir / "manifest.json").write_text(
        json.dumps({"app.py": {"existed": True, "applied_hash": file_hash(source / "app.py")}}),
        encoding="utf-8",
    )

    manager = RunManager(
        settings=_settings(tmp_path),
        store=RunStore(records),
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("must not resume")),
    )
    client = _client(manager, ApplyService(manager.store, verification=_PassingVerification()))

    reconciled = client.get("/api/runs/run-stuck").json()
    assert reconciled["phase"] == "apply_failed"
    assert reconciled["apply_result"]["backup_path"] == str(backup_dir)

    restore_response = client.post("/api/runs/run-stuck/restore", json={"confirmed": True})

    assert restore_response.status_code == 200
    assert restore_response.json()["status"] == "restored"
    assert (source / "app.py").read_text(encoding="utf-8") == "old\n"


def test_public_snapshots_omit_durable_source_hashes(tmp_path: Path) -> None:
    source = _source(tmp_path)
    manager = _manager(tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id))
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "hash privately"},
    ).json()["run_id"]
    _wait_for_phase(client, run_id, "approved")

    durable = manager.store.load(run_id)
    public = client.get(f"/api/runs/{run_id}").json()
    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        terminal = websocket.receive_json()

    assert durable.source_hashes["app.py"]
    assert "source_hashes" not in public
    assert terminal["kind"] == "snapshot"
    assert "source_hashes" not in terminal["snapshot"]


def test_start_persists_queued_snapshot_immediately_with_empty_source_hashes(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    source = _source(tmp_path)
    store = RunStore(tmp_path / "records")
    release_hash = threading.Event()

    def blocking_snapshot(_root: Path) -> dict[str, str | None]:
        assert release_hash.wait(timeout=2), "worker never called snapshot_project"
        return {"app.py": "deadbeef"}

    monkeypatch.setattr("engineering_team.run_api.snapshot_project", blocking_snapshot)
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )
    client = _client(manager)

    response = client.post("/api/runs", json={"projectPath": str(source), "message": "quick"})
    run_id = response.json()["run_id"]
    snapshot = store.load(run_id)

    assert response.status_code == 202
    assert snapshot.phase in {RunPhase.QUEUED, RunPhase.PREPARING}
    assert snapshot.source_hashes == {}
    release_hash.set()


def test_source_hashes_populated_before_workspace_copy_runs(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    source = _source(tmp_path)
    store = RunStore(tmp_path / "records")
    captured: dict[str, Any] = {}

    def capture_copy(run_id: str, _source: Path, _root: str) -> Path:
        captured["hashes"] = store.load(run_id).source_hashes
        captured["phase"] = store.load(run_id).phase
        destination = tmp_path / "workspace-copy"
        destination.mkdir(exist_ok=True)
        return destination

    monkeypatch.setattr("engineering_team.run_api.create_run_copy", capture_copy)
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda snapshot, _emit: _completed_state(snapshot.run_id),
    )
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "hash before copy"},
    ).json()["run_id"]
    _wait_for_phase(client, run_id, "approved")

    assert captured["phase"] is RunPhase.PREPARING
    assert captured["hashes"].get("app.py")


def test_queued_run_is_persisted_before_copy_and_copy_failure_remains_queryable(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    source = _source(tmp_path)
    store = RunStore(tmp_path / "records")
    entered_copy, release_copy = threading.Event(), threading.Event()
    observed_phase: list[RunPhase] = []
    requested_transitions: list[RunPhase] = []
    transition = store.transition

    def fail_copy(run_id: str, _source: Path, _root: str) -> Path:
        observed_phase.append(store.load(run_id).phase)
        entered_copy.set()
        release_copy.wait(timeout=2)
        raise OSError("copy failed with api_key=top-secret")

    def record_transition(run_id: str, phase: RunPhase) -> RunSnapshot:
        requested_transitions.append(phase)
        return transition(run_id, phase)

    monkeypatch.setattr("engineering_team.run_api.create_run_copy", fail_copy)
    monkeypatch.setattr(store, "transition", record_transition)
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )
    client = _client(manager)
    response = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "copy safely"},
    )
    run_id = response.json()["run_id"]
    assert entered_copy.wait(timeout=2)
    assert store.load(run_id).workspace_path == str((tmp_path / "workspaces" / run_id).resolve())
    release_copy.set()
    failed = _wait_for_phase(client, run_id, "failed")

    assert response.status_code == 202
    assert observed_phase == [RunPhase.PREPARING]
    assert requested_transitions == [RunPhase.PREPARING]
    assert failed["report"]["review"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert "top-secret" not in str(failed)
    assert client.get(f"/api/runs/{run_id}").status_code == 200


def test_real_execution_boundary_writes_only_to_isolated_workspace(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    source = _source(tmp_path)
    captured: dict[str, Any] = {}

    def execute(_settings: Settings, **kwargs: Any) -> tuple[dict[str, Any], None, float, bool]:
        captured.update(kwargs)
        return _completed_state(kwargs["run_id"]), None, 0.0, False

    monkeypatch.setattr("engineering_team.run_api.execute_on_project", execute)
    manager = RunManager(settings=_settings(tmp_path), store=RunStore(tmp_path / "records"))
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "make the change"},
    ).json()["run_id"]
    snapshot = _wait_for_phase(client, run_id, "approved")

    assert Path(captured["project_path"]) == Path(snapshot["workspace_path"])
    assert Path(captured["project_path"]) != source.resolve()
    assert captured["authorize_writes"] is False
    assert captured["specification"] == "make the change"
    assert captured["run_id"] == run_id


@pytest.mark.parametrize("configured_location", ["same", "descendant", "same-different-case"])
def test_workspace_falls_back_outside_source_when_configured_root_overlaps(
    tmp_path: Path, monkeypatch: Any, configured_location: str,
) -> None:
    source = _source(tmp_path)
    if configured_location == "same":
        configured_root = source
    elif configured_location == "descendant":
        configured_root = source / "configured-runs"
    else:
        configured_root = Path(str(source).swapcase())
    copied_roots: list[Path] = []

    def copy_without_recursing(run_id: str, _source: Path, root: str | Path) -> Path:
        root_path = Path(root).resolve()
        copied_roots.append(root_path)
        destination = root_path / run_id
        destination.mkdir(parents=True)
        return destination

    def executor(snapshot: RunSnapshot, _emit: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        (Path(snapshot.workspace_path) / "agent-output.py").write_text(
            "changed = True\n", encoding="utf-8",
        )
        return _completed_state(snapshot.run_id)

    monkeypatch.setattr("engineering_team.run_api.create_run_copy", copy_without_recursing)
    manager = RunManager(
        settings=Settings(workspace_root=str(configured_root)),
        store=RunStore(tmp_path / "records"),
        executor=executor,
    )
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "stay isolated"},
    ).json()["run_id"]
    snapshot = _wait_for_phase(client, run_id, "approved")
    workspace = Path(snapshot["workspace_path"])

    assert workspace != source
    assert source not in workspace.parents
    assert workspace not in source.parents
    assert copied_roots == [workspace.parent]
    assert not (source / "agent-output.py").exists()


def test_event_get_and_websocket_reconnect_replay_only_missing_events(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "records")
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="work", phase=RunPhase.APPROVED,
        source_hashes={"secret.py": "durable-only"},
        report={"review": {"status": "APPROVED"}},
    ))
    for name in ("one", "two", "three"):
        store.append_event("run-a", _event(name))
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: _completed_state("run-a"),
    )
    client = _client(manager)

    response = client.get("/api/runs/run-a/events?after=1")
    with client.websocket_connect("/ws/runs/run-a?after=1") as websocket:
        second, third = websocket.receive_json(), websocket.receive_json()
        terminal = websocket.receive_json()

    assert response.status_code == 200
    assert [item["sequence"] for item in response.json()] == [2, 3]
    assert second == {"kind": "event", "sequence": 2, "payload": _event("two")}
    assert third == {"kind": "event", "sequence": 3, "payload": _event("three")}
    assert terminal["kind"] == "snapshot"
    assert terminal["snapshot"]["run_id"] == "run-a"
    assert "source_hashes" not in terminal["snapshot"]
    assert client.get("/api/runs/run-a").status_code == 200


def test_websocket_publishes_active_phase_transitions_without_agent_events(tmp_path: Path, monkeypatch: Any) -> None:
    store = RunStore(tmp_path / "records")
    manager = RunManager(settings=_settings(tmp_path), store=store,
                         executor=lambda *_: _completed_state("run-live"))
    store.create(RunSnapshot(
        run_id="run-live", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="work", phase=RunPhase.QUEUED,
        source_hashes={"private": "must not leave backend"},
    ))
    waits = 0

    def advance(*_args):
        nonlocal waits
        waits += 1
        if waits == 1:
            store.transition("run-live", RunPhase.PREPARING)
            store.transition("run-live", RunPhase.RUNNING)
        else:
            store.finish("run-live", {"review": {"status": "APPROVED"}}, RunPhase.APPROVED)

    monkeypatch.setattr(store, "wait_after", advance)
    with _client(manager).websocket_connect("/ws/runs/run-live") as websocket:
        first = websocket.receive_json()
        assert first["snapshot"]["phase"] == "queued"
        running = websocket.receive_json()
        terminal = websocket.receive_json()
    assert running["snapshot"]["phase"] == "running"
    assert terminal["snapshot"]["phase"] == "approved"
    assert "source_hashes" not in running["snapshot"]


def test_websocket_replays_event_appended_during_terminal_transition(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    store = RunStore(tmp_path / "records")
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: _completed_state("run-race"),
    )
    store.create(RunSnapshot(
        run_id="run-race", project_path=str(tmp_path / "source"),
        workspace_path=str(tmp_path / "copy"), message="work", phase=RunPhase.RUNNING,
        source_hashes={},
    ))
    load = store.load
    load_count = 0

    def finish_between_replay_and_terminal_read(run_id: str) -> RunSnapshot:
        nonlocal load_count
        load_count += 1
        if load_count == 2:
            store.append_event(run_id, _event("last"))
            store.finish(
                run_id,
                {"review": {"status": "APPROVED"}},
                RunPhase.APPROVED,
            )
        return load(run_id)

    monkeypatch.setattr(store, "load", finish_between_replay_and_terminal_read)
    client = _client(manager)

    with client.websocket_connect("/ws/runs/run-race") as websocket:
        event = websocket.receive_json()
        terminal = websocket.receive_json()

    assert event == {"kind": "event", "sequence": 1, "payload": _event("last")}
    assert terminal["kind"] == "snapshot"
    assert [item["sequence"] for item in terminal["snapshot"]["events"]] == [1]


def test_websocket_disconnect_does_not_discard_active_or_terminal_run(tmp_path: Path) -> None:
    source = _source(tmp_path)
    emitted, release = threading.Event(), threading.Event()

    def executor(
        snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        emit(_event("first"))
        emitted.set()
        release.wait(timeout=2)
        return _completed_state(snapshot.run_id)

    manager = _manager(tmp_path, executor)
    client = _client(manager)
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "keep it"},
    ).json()["run_id"]
    assert emitted.wait(timeout=2)

    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        assert websocket.receive_json()["sequence"] == 1
    assert client.get(f"/api/runs/{run_id}").status_code == 200

    release.set()
    _wait_for_phase(client, run_id, "approved")
    with client.websocket_connect(f"/ws/runs/{run_id}?after=1") as websocket:
        assert websocket.receive_json()["kind"] == "snapshot"
    assert client.get(f"/api/runs/{run_id}").status_code == 200


def test_post_validates_the_exact_launch_contract(tmp_path: Path) -> None:
    source = _source(tmp_path)
    client = _client(_manager(
        tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id),
    ))

    missing_message = client.post("/api/runs", json={"projectPath": str(source)})
    old_public_fields = client.post("/api/runs", json={
        "projectPath": str(source), "message": "work",
        "testSpecification": "tests", "writeMode": "dry_run",
    })

    assert missing_message.status_code == 422
    assert old_public_fields.status_code == 422


def test_missing_runs_return_not_found_for_http_and_websocket(tmp_path: Path) -> None:
    client = _client(_manager(
        tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id),
    ))

    assert client.get("/api/runs/not-a-run").status_code == 404
    assert client.get("/api/runs/not-a-run/events").status_code == 404
    with client.websocket_connect("/ws/runs/not-a-run") as websocket:
        assert websocket.receive_json() == {"detail": "run_id not found"}


def test_executor_error_is_safe_and_persisted_once(tmp_path: Path) -> None:
    source = _source(tmp_path)

    def executor(*_: Any) -> dict[str, Any]:
        raise RuntimeError("provider failed with api_key=top-secret")

    client = _client(_manager(tmp_path, executor))
    run_id = client.post(
        "/api/runs", json={"projectPath": str(source), "message": "alpha"},
    ).json()["run_id"]
    failed = _wait_for_phase(client, run_id, "failed")

    events = client.get(f"/api/runs/{run_id}/events").json()
    assert len(events) == 1
    assert events[0]["payload"]["type"] == "error"
    assert "top-secret" not in events[0]["payload"]["status_message"]
    assert failed["report"]["review"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert len(failed["report"]["errors"]) == 1


def test_post_to_real_langgraph_to_websocket_delivers_real_final_report(tmp_path: Path) -> None:
    source = _source(tmp_path)
    visited: list[str] = []

    def executor(
        snapshot: RunSnapshot, emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        sequence = 0

        def observe(trace_event: dict[str, Any]) -> None:
            nonlocal sequence
            if trace_event["name"] in {
                "Product", "Architecture", "Developer", "Security", "Testing", "Reviewer",
            }:
                visited.append(trace_event["name"])
            sequence += 1
            emit(run_event_from_trace(
                run_id=snapshot.run_id, sequence=sequence,
                trace_event=trace_event, observed_at=sequence,
            ))

        trace = EventForwardingTrace(
            TraceSession(trace_id="test-trace", run_id=snapshot.run_id, live=False), observe,
        )
        return build_engineering_graph(trace=trace).invoke({
            "run_id": snapshot.run_id, "requirement": snapshot.message,
            "repository_context": {
                "authorized": True, "project_path": snapshot.workspace_path,
            },
        })

    client = _client(_manager(tmp_path, executor))
    run_id = client.post("/api/runs", json={
        "projectPath": str(source), "message": "Add a deterministic health operation.",
    }).json()["run_id"]

    payloads: list[dict[str, Any]] = []
    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        while True:
            payload = websocket.receive_json()
            payloads.append(payload)
            if payload["kind"] == "snapshot" and payload["snapshot"]["phase"] not in {
                "queued", "preparing", "running", "applying",
            }:
                break

    assert visited == ["Product", "Architecture", "Developer", "Security", "Testing", "Reviewer"]
    assert payloads[-1]["snapshot"]["report"]["review"]["status"] == "APPROVED"
    assert payloads[-1]["snapshot"]["report"]["route_history"][-1]["decision"] == "APPROVED"


def test_apply_endpoint_writes_source_and_persists_applied_result(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    client, store, project_path = _approved_run_client(tmp_path, source, workspace, ["app.py"])

    response = client.post(
        "/api/runs/run-a/apply", json={"projectPath": project_path, "confirmed": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert (source / "app.py").read_text(encoding="utf-8") == "new\n"
    assert store.load("run-a").phase is RunPhase.APPLIED


def test_apply_endpoint_rejects_unapproved_run_with_409(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    store = RunStore(tmp_path / "records")
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.RUNNING, source_hashes={},
    ))
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )
    client = _client(manager, ApplyService(store, verification=_PassingVerification()))

    response = client.post(
        "/api/runs/run-a/apply",
        json={"projectPath": str(source.resolve()), "confirmed": True},
    )

    assert response.status_code == 409


def test_apply_endpoint_rejects_mismatched_project_path_with_409(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    client, _store, _project_path = _approved_run_client(tmp_path, source, workspace, ["app.py"])
    other = tmp_path / "elsewhere"
    other.mkdir()

    response = client.post(
        "/api/runs/run-a/apply", json={"projectPath": str(other), "confirmed": True},
    )

    assert response.status_code == 409


def test_apply_endpoint_rejects_unconfirmed_request_with_422(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    client, _store, project_path = _approved_run_client(tmp_path, source, workspace, ["app.py"])

    response = client.post(
        "/api/runs/run-a/apply", json={"projectPath": project_path, "confirmed": False},
    )

    assert response.status_code == 422
    assert (source / "app.py").read_text(encoding="utf-8") == "old\n"


def test_apply_endpoint_is_idempotent_on_repeat(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    client, _store, project_path = _approved_run_client(tmp_path, source, workspace, ["app.py"])
    body = {"projectPath": project_path, "confirmed": True}

    first = client.post("/api/runs/run-a/apply", json=body)
    mtime_before = (source / "app.py").stat().st_mtime_ns
    second = client.post("/api/runs/run-a/apply", json=body)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert (source / "app.py").stat().st_mtime_ns == mtime_before


def test_restore_endpoint_reverts_apply_failed_run_and_rejects_without_backup(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    (source / "app.py").write_text("old\n", encoding="utf-8")
    (workspace / "app.py").write_text("new\n", encoding="utf-8")
    store = RunStore(tmp_path / "records")
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes=snapshot_project(source),
        changed_paths=["app.py"], report={"review": {"status": "APPROVED"}},
    ))
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )

    class _FailingVerification:
        def run(self, project: Path) -> tuple[int, str]:
            return 1, "1 failed"

    apply_service = ApplyService(store, verification=_FailingVerification())
    client = _client(manager, apply_service)
    client.post(
        "/api/runs/run-a/apply",
        json={"projectPath": str(source.resolve()), "confirmed": True},
    )

    store.create(RunSnapshot(
        run_id="run-b", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPROVED, source_hashes={}, report={"review": {"status": "APPROVED"}},
    ))
    no_backup_response = _client(manager, apply_service).post(
        "/api/runs/run-b/restore", json={"confirmed": True},
    )

    response = client.post("/api/runs/run-a/restore", json={"confirmed": True})

    assert no_backup_response.status_code == 409
    assert response.status_code == 200
    assert response.json()["status"] == "restored"
    assert (source / "app.py").read_text(encoding="utf-8") == "old\n"
    assert store.load("run-a").phase is RunPhase.APPROVED


def test_restore_endpoint_returns_structured_409_when_apply_failed_with_no_backup(
    tmp_path: Path,
) -> None:
    """apply_failed via write-failure/auto-rollback has backup_path None; restoring
    must return a clean structured 409, not an unhandled 500 from ApplyService."""
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    store = RunStore(tmp_path / "records")
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPLY_FAILED, source_hashes={},
        apply_result=ApplyResult(
            status="apply_failed", written_paths=[], backup_path=None,
            message="apply failed and was rolled back: boom",
        ),
    ))
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )
    client = _client(manager, ApplyService(store, verification=_PassingVerification()))

    response = client.post("/api/runs/run-a/restore", json={"confirmed": True})

    assert response.status_code == 409
    body = response.json()["detail"]
    assert body["code"] == "NO_RESTORABLE_BACKUP"
    assert body["recoverable"] is False


def test_error_envelopes_are_structured_across_run_endpoints(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    client = _client(_manager(
        tmp_path, lambda snapshot, _emit: _completed_state(snapshot.run_id),
    ))

    not_found = client.get("/api/runs/does-not-exist")
    bad_project = client.post(
        "/api/runs", json={"projectPath": str(tmp_path / "missing"), "message": "hi"},
    )

    for response, expected_status in ((not_found, 404), (bad_project, 422)):
        assert response.status_code == expected_status
        detail = response.json()["detail"]
        assert set(detail) >= {"code", "message", "recoverable"}
        assert isinstance(detail["recoverable"], bool)


def test_restore_endpoint_rejects_unconfirmed_request_with_422(tmp_path: Path) -> None:
    source, workspace = tmp_path / "source", tmp_path / "workspace"
    source.mkdir(); workspace.mkdir()
    store = RunStore(tmp_path / "records")
    store.create(RunSnapshot(
        run_id="run-a", project_path=str(source.resolve()),
        workspace_path=str(workspace.resolve()), message="work",
        phase=RunPhase.APPLY_FAILED, source_hashes={},
        apply_result=None,
    ))
    manager = RunManager(
        settings=_settings(tmp_path), store=store,
        executor=lambda *_: (_ for _ in ()).throw(AssertionError("executor must not run")),
    )
    client = _client(manager, ApplyService(store, verification=_PassingVerification()))

    response = client.post("/api/runs/run-a/restore", json={"confirmed": False})

    assert response.status_code == 422
