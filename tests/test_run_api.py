from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engineering_team.config import Settings
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.langfuse import TraceSession
from engineering_team.run_api import RunManager, create_runs_router
from engineering_team.run_events import (
    EventForwardingTrace,
    final_report_from_state,
    run_event_from_trace,
)
from engineering_team.runs import RunPhase, RunSnapshot, RunStore


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


def _client(manager: RunManager) -> TestClient:
    app = FastAPI()
    app.include_router(create_runs_router(manager))
    return TestClient(app)


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
        "workspace_changed", "source_applied", "review", "errors",
        "rag_evidence", "tool_results",
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


def test_queued_run_is_persisted_before_copy_and_copy_failure_remains_queryable(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    source = _source(tmp_path)
    store = RunStore(tmp_path / "records")
    entered_copy, release_copy = threading.Event(), threading.Event()
    observed_phase: list[RunPhase] = []

    def fail_copy(run_id: str, _source: Path, _root: str) -> Path:
        observed_phase.append(store.load(run_id).phase)
        entered_copy.set()
        release_copy.wait(timeout=2)
        raise OSError("copy failed with api_key=top-secret")

    monkeypatch.setattr("engineering_team.run_api.create_run_copy", fail_copy)
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
    assert captured["authorize_writes"] is True
    assert captured["specification"] == "make the change"
    assert captured["run_id"] == run_id


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
            if payload["kind"] == "snapshot":
                break

    assert visited == ["Product", "Architecture", "Developer", "Security", "Testing", "Reviewer"]
    assert payloads[-1]["snapshot"]["report"]["review"]["status"] == "APPROVED"
    assert payloads[-1]["snapshot"]["report"]["route_history"][-1]["decision"] == "APPROVED"
