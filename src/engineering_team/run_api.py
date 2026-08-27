"""FastAPI transport for real, isolated engineering workflow runs."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.websockets import WebSocketDisconnect

from engineering_team.apply_run import execute_on_project
from engineering_team.config import Settings
from engineering_team.guardrails.secrets import redact_secrets
from engineering_team.run_events import failure_state, final_report_from_state, run_event_from_trace
from engineering_team.workspace.isolation import create_run_copy

RunExecutor = Callable[[str, dict[str, Any], Callable[[dict[str, Any]], None]], dict[str, Any]]


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    project_path: str = Field(alias="projectPath", min_length=1)
    specification: str = Field(min_length=1)
    test_specification: str = Field(alias="testSpecification")
    write_mode: str = Field(alias="writeMode", pattern="^(dry_run|authorized)$")

    @field_validator("project_path")
    @classmethod
    def existing_project(cls, value: str) -> str:
        if not Path(value).expanduser().resolve().is_dir():
            raise ValueError("projectPath must reference an existing directory")
        return value


class RunRecord:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._items: list[dict[str, Any]] = []
        self._finished = False
        self._condition = threading.Condition()

    def publish(self, item: dict[str, Any], *, terminal: bool = False) -> None:
        with self._condition:
            if self._finished:
                return
            self._items.append(item)
            self._finished = terminal
            self._condition.notify_all()

    def next_item(self, index: int) -> tuple[dict[str, Any] | None, bool]:
        with self._condition:
            while index >= len(self._items) and not self._finished:
                self._condition.wait(timeout=1)
            item = self._items[index] if index < len(self._items) else None
            return item, self._finished and index + (item is not None) >= len(self._items)


class RunManager:
    def __init__(self, *, executor: RunExecutor | None = None) -> None:
        self._executor = executor or self._execute_real_run
        self._runs: dict[str, RunRecord] = {}
        self._lock = threading.Lock()

    def start(self, config: dict[str, Any]) -> str:
        run_id = f"run-{uuid.uuid4()}"
        record = RunRecord(run_id)
        with self._lock:
            self._runs[run_id] = record
        threading.Thread(target=self._worker, args=(record, config), daemon=True).start()
        return run_id

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def discard(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def _worker(self, record: RunRecord, config: dict[str, Any]) -> None:
        try:
            state = self._executor(record.run_id, config, record.publish)
        except Exception as exc:  # noqa: BLE001 - public boundary must terminate every run safely.
            message = redact_secrets(str(exc))
            record.publish({
                "id": f"{record.run_id}-error", "name": "workflow error", "type": "error",
                "level": "error", "status_message": message,
                "metadata": {"code": "WORKFLOW_ERROR"},
                "agent": "human_review", "iteration": 0, "at": int(time.time() * 1000),
            })
            state = failure_state(record.run_id, message)
        record.publish(final_report_from_state(state), terminal=True)

    @staticmethod
    def _execute_real_run(
        run_id: str, config: dict[str, Any], emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        settings = Settings()
        isolated = create_run_copy(run_id, config["projectPath"], settings.workspace_root)
        sequence = 0

        def observe(trace_event: dict[str, Any]) -> None:
            nonlocal sequence
            if trace_event.get("name") == "FinalReport":
                return
            sequence += 1
            emit(run_event_from_trace(
                run_id=run_id, sequence=sequence, trace_event=trace_event,
            ))

        state, _trace, _duration, _cloud_first = execute_on_project(
            settings,
            project_path=isolated,
            specification=config["specification"],
            test_specification=config["testSpecification"],
            authorize_writes=config["writeMode"] == "authorized",
            run_id=run_id,
            event_observer=observe,
        )
        return state


def create_runs_router(manager: RunManager | None = None) -> APIRouter:
    run_manager = manager or RunManager()
    router = APIRouter()

    @router.post("/api/runs", status_code=202)
    def start_run(request: LaunchRequest) -> dict[str, str]:
        return {"run_id": run_manager.start(request.model_dump(by_alias=True))}

    @router.websocket("/ws/runs/{run_id}")
    async def run_events(websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        record = run_manager.get(run_id)
        if record is None:
            await websocket.send_json({"detail": "run_id not found"})
            await websocket.close(code=4404)
            return
        index = 0
        try:
            while True:
                item, terminal = await __import__("asyncio").to_thread(record.next_item, index)
                if item is not None:
                    await websocket.send_json(item)
                    index += 1
                if terminal:
                    await websocket.close(code=1000)
                    break
        except WebSocketDisconnect:
            pass
        finally:
            if terminal if "terminal" in locals() else False:
                run_manager.discard(run_id)

    return router


router = create_runs_router()
