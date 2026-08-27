from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.langfuse import TraceSession
from engineering_team.run_api import RunManager, create_runs_router
from engineering_team.run_events import (
    EventForwardingTrace,
    final_report_from_state,
    run_event_from_trace,
)


def _completed_state() -> dict[str, Any]:
    return {
        "run_id": "run-1",
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


def test_trace_event_matches_the_public_run_event_contract() -> None:
    event = run_event_from_trace(
        run_id="run-1",
        sequence=3,
        trace_event={
            "name": "model call",
            "type": "generation",
            "level": None,
            "status_message": "completed",
            "metadata": {"agent": "Product", "iteration": 2, "provider": "ollama"},
            "input": {"task": "specify"},
            "output": {"ok": True},
            "model": "qwen3.5:4b",
            "usage_details": {"input_tokens": 10, "output_tokens": 20, "latency_ms": 120},
        },
        observed_at=1234,
    )

    assert event == {
        "id": "run-1-3",
        "name": "model call",
        "type": "model",
        "level": "info",
        "status_message": "completed",
        "metadata": {"agent": "Product", "iteration": 2, "provider": "ollama"},
        "model": "qwen3.5:4b",
        "input": '{"task":"specify"}',
        "output": '{"ok":true}',
        "usage_details": {"input_tokens": 10, "output_tokens": 20, "latency_ms": 120},
        "agent": "product",
        "iteration": 2,
        "at": 1234,
    }


def test_final_report_is_an_exact_projection_of_real_state() -> None:
    report = final_report_from_state(_completed_state())

    assert set(report) == {
        "route_history", "model_usage", "changed_files", "applied_diff",
        "review", "errors", "rag_evidence", "tool_results",
    }
    assert report["review"]["status"] == "APPROVED"
    assert report["changed_files"][0]["additions"] == 1
    assert report["changed_files"][0]["deletions"] == 1
    assert report["model_usage"] == [{
        "agent": "product", "model": "qwen3.5:4b", "provider": "local",
        "calls": 1, "input_tokens": 10, "output_tokens": 20, "avg_latency_ms": 120,
    }]
    assert report["tool_results"][0]["agent"] == "testing"


def test_post_buffers_ordered_events_until_websocket_connects(tmp_path: Path) -> None:
    emitted = threading.Event()
    release = threading.Event()

    def executor(run_id: str, config: dict[str, Any], emit: Any) -> dict[str, Any]:
        emit({"id": f"{run_id}-1", "name": "first", "type": "rag", "level": "info",
              "status_message": "one", "metadata": {}, "agent": "product",
              "iteration": 0, "at": 1})
        emit({"id": f"{run_id}-2", "name": "second", "type": "tool", "level": "info",
              "status_message": "two", "metadata": {}, "agent": "architecture",
              "iteration": 0, "at": 2})
        emitted.set()
        release.wait(timeout=2)
        return _completed_state()

    manager = RunManager(executor=executor)
    app = FastAPI()
    app.include_router(create_runs_router(manager))
    client = TestClient(app)
    response = client.post("/api/runs", json={
        "projectPath": str(tmp_path), "specification": "Implement the limit.",
        "testSpecification": "Verify the limit.", "writeMode": "dry_run",
    })
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert emitted.wait(timeout=2)
    release.set()

    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        assert websocket.receive_json()["name"] == "first"
        assert websocket.receive_json()["name"] == "second"
        final = websocket.receive_json()
    assert final["review"]["status"] == "APPROVED"


def test_post_validates_the_exact_launch_contract(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_runs_router(RunManager(executor=lambda *_: _completed_state())))
    client = TestClient(app)

    missing_specification = client.post("/api/runs", json={
        "projectPath": str(tmp_path), "testSpecification": "tests", "writeMode": "dry_run",
    })
    extra_public_field = client.post("/api/runs", json={
        "projectPath": str(tmp_path), "specification": "work",
        "testSpecification": "tests", "writeMode": "dry_run", "trace_id": "invented",
    })

    assert missing_specification.status_code == 422
    assert extra_public_field.status_code == 422


def test_invalid_run_id_is_rejected() -> None:
    app = FastAPI()
    app.include_router(create_runs_router(RunManager(executor=lambda *_: _completed_state())))
    client = TestClient(app)

    with client.websocket_connect("/ws/runs/not-a-run") as websocket:
        assert websocket.receive_json() == {"detail": "run_id not found"}


def test_concurrent_runs_do_not_share_events(tmp_path: Path) -> None:
    def executor(run_id: str, config: dict[str, Any], emit: Any) -> dict[str, Any]:
        emit({"id": f"{run_id}-1", "name": config["specification"], "type": "rag",
              "level": "info", "status_message": "real", "metadata": {},
              "agent": "product", "iteration": 0, "at": 1})
        return _completed_state()

    manager = RunManager(executor=executor)
    app = FastAPI()
    app.include_router(create_runs_router(manager))
    client = TestClient(app)
    ids = [client.post("/api/runs", json={
        "projectPath": str(tmp_path), "specification": value,
        "testSpecification": "tests", "writeMode": "dry_run",
    }).json()["run_id"] for value in ("alpha", "beta")]

    names = []
    for run_id in ids:
        with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
            names.append(websocket.receive_json()["name"])
            websocket.receive_json()
    assert names == ["alpha", "beta"]


def test_executor_error_is_safe_and_terminates_once(tmp_path: Path) -> None:
    def executor(*_: Any) -> dict[str, Any]:
        raise RuntimeError("provider failed with api_key=top-secret")

    manager = RunManager(executor=executor)
    app = FastAPI()
    app.include_router(create_runs_router(manager))
    client = TestClient(app)
    run_id = client.post("/api/runs", json={
        "projectPath": str(tmp_path), "specification": "alpha",
        "testSpecification": "tests", "writeMode": "dry_run",
    }).json()["run_id"]

    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        error = websocket.receive_json()
        final = websocket.receive_json()
    assert error["type"] == "error"
    assert "top-secret" not in error["status_message"]
    assert final["review"]["status"] == "HUMAN_REVIEW_REQUIRED"
    assert len(final["errors"]) == 1


def test_post_to_real_langgraph_to_websocket_delivers_real_final_report(tmp_path: Path) -> None:
    visited: list[str] = []

    def executor(run_id: str, config: dict[str, Any], emit: Any) -> dict[str, Any]:
        sequence = 0

        def observe(trace_event: dict[str, Any]) -> None:
            nonlocal sequence
            if trace_event["name"] in {
                "Product", "Architecture", "Developer", "Security", "Testing", "Reviewer"
            }:
                visited.append(trace_event["name"])
            sequence += 1
            emit(run_event_from_trace(
                run_id=run_id, sequence=sequence, trace_event=trace_event, observed_at=sequence,
            ))

        trace = EventForwardingTrace(TraceSession(
            trace_id="test-trace", run_id=run_id, live=False,
        ), observe
        )
        return build_engineering_graph(trace=trace).invoke({
            "run_id": run_id,
            "requirement": config["specification"],
            "repository_context": {"authorized": False, "project_path": str(tmp_path)},
        })

    app = FastAPI()
    app.include_router(create_runs_router(RunManager(executor=executor)))
    client = TestClient(app)
    run_id = client.post("/api/runs", json={
        "projectPath": str(tmp_path), "specification": "Add a deterministic health operation.",
        "testSpecification": "Verify the operation.", "writeMode": "dry_run",
    }).json()["run_id"]

    payloads: list[dict[str, Any]] = []
    with client.websocket_connect(f"/ws/runs/{run_id}") as websocket:
        while True:
            payload = websocket.receive_json()
            payloads.append(payload)
            if "route_history" in payload:
                break

    assert visited == ["Product", "Architecture", "Developer", "Security", "Testing", "Reviewer"]
    assert payloads[-1]["review"]["status"] == "APPROVED"
    assert payloads[-1]["route_history"][-1]["decision"] == "APPROVED"
