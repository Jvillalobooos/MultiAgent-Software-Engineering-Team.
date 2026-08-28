"""FastAPI transport for durable, isolated engineering workflow runs."""

from __future__ import annotations

import asyncio
import os
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, WebSocket
from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocketDisconnect

from engineering_team.apply_run import execute_on_project
from engineering_team.apply_service import ApplyService, snapshot_project
from engineering_team.config import Settings
from engineering_team.guardrails.secrets import redact_secrets
from engineering_team.run_events import failure_state, final_report_from_state, run_event_from_trace
from engineering_team.runs import ApplyResult, RunPhase, RunSnapshot, RunStore
from engineering_team.workspace.isolation import create_run_copy

RunExecutor = Callable[
    [RunSnapshot, Callable[[dict[str, Any]], None]],
    dict[str, Any],
]

_ACTIVE_PHASES = {
    RunPhase.QUEUED,
    RunPhase.PREPARING,
    RunPhase.RUNNING,
    RunPhase.APPLYING,
}
_INTERRUPTED_PHASES = {RunPhase.QUEUED, RunPhase.PREPARING, RunPhase.RUNNING}
_SNAPSHOT_FIELDS = (
    "run_id",
    "project_path",
    "workspace_path",
    "message",
    "test_spec",
    "authorize_writes",
    "phase",
    "trace_id",
    "events",
    "report",
    "changed_paths",
    "apply_result",
    "created_at",
    "updated_at",
)
def _error(code: str, message: str, *, recoverable: bool, **details: Any) -> dict[str, Any]:
    """Build the stable {code, message, recoverable, details?} envelope used for every
    run/apply/restore error -- the backend, not the frontend, owns recoverability."""
    body: dict[str, Any] = {"code": code, "message": message, "recoverable": recoverable}
    if details:
        body["details"] = details
    return body


class LaunchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    project_path: str = Field(alias="projectPath", min_length=1)
    message: str = Field(min_length=1)
    test_specification: str | None = Field(default=None, alias="testSpec")
    authorize_writes: bool = Field(default=False, alias="authorizeWrites")


class ApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    project_path: str = Field(alias="projectPath", min_length=1)
    confirmed: Literal[True]


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    confirmed: Literal[True]


def _public_snapshot(snapshot: RunSnapshot) -> dict[str, Any]:
    """Explicitly project the durable record without its conflict-detection hashes."""
    durable = snapshot.model_dump(mode="json")
    return {field: durable[field] for field in _SNAPSHOT_FIELDS}


def _normcase_path(path: Path) -> Path:
    """Normalize a resolved path's casing for filesystem-appropriate comparison."""
    return Path(os.path.normcase(str(path)))


def _workspace_root(source: Path, configured_root: str | Path) -> Path:
    configured = Path(configured_root).expanduser().resolve()
    normalized_configured = _normcase_path(configured)
    normalized_source = _normcase_path(source)
    if normalized_configured == normalized_source or normalized_source in normalized_configured.parents:
        return (Path(tempfile.gettempdir()).resolve() / "nova" / "runs").resolve()
    return configured


class RunManager:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        store: RunStore | None = None,
        executor: RunExecutor | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.store = store or RunStore(self.settings.workspace_root)
        self._executor = executor or self._execute_real_run
        self._reconcile_interrupted_runs()

    def _reconcile_interrupted_runs(self) -> None:
        for summary in self.store.list_summaries():
            if summary.phase in _INTERRUPTED_PHASES:
                self._fail(
                    summary.run_id,
                    RuntimeError("Run interrupted before completion; service restarted."),
                )
            elif summary.phase is RunPhase.APPLYING:
                self._reconcile_interrupted_apply(summary.run_id)

    def _reconcile_interrupted_apply(self, run_id: str) -> None:
        """A process death mid-apply leaves the run stuck in APPLYING forever unless
        reconciled: transition it to apply_failed so it becomes queryable and, when a
        valid backup manifest exists, restorable. Never inspect or touch the actual
        source project files here -- only check whether a manifest was written."""
        backup_dir = self.store.root / "_backups" / run_id
        manifest_path = backup_dir / "manifest.json"
        backup_path = str(backup_dir) if manifest_path.exists() else None
        result = ApplyResult(
            status="apply_failed",
            backup_path=backup_path,
            message=(
                "interrupted mid-apply; verify project state manually"
                + ("" if backup_path else " (no backup manifest found)")
            ),
        )
        self.store.record_apply_result(run_id, result)
        self.store.transition(run_id, RunPhase.APPLY_FAILED)

    def start(self, request: LaunchRequest) -> str:
        run_id = f"run-{uuid.uuid4()}"
        source = Path(request.project_path).expanduser().resolve()
        workspace_root = _workspace_root(source, self.settings.workspace_root)
        workspace = (workspace_root / run_id).resolve()
        snapshot = RunSnapshot(
            run_id=run_id,
            project_path=str(source),
            workspace_path=str(workspace),
            message=request.message.strip(),
            test_spec=request.test_specification,
            authorize_writes=request.authorize_writes,
            phase=RunPhase.QUEUED,
            source_hashes={},
        )
        self.store.create(snapshot)
        threading.Thread(target=self._worker, args=(run_id,), daemon=True).start()
        return run_id

    def get(self, run_id: str) -> RunSnapshot | None:
        try:
            return self.store.load(run_id)
        except KeyError:
            return None

    def _worker(self, run_id: str) -> None:
        try:
            self.store.transition(run_id, RunPhase.PREPARING)
            snapshot = self.store.load(run_id)
            self.store.record_source_hashes(run_id, snapshot_project(Path(snapshot.project_path)))
            snapshot = self.store.load(run_id)
            create_run_copy(run_id, snapshot.project_path, Path(snapshot.workspace_path).parent)
            self.store.transition(run_id, RunPhase.RUNNING)
            running = self.store.load(run_id)
            state = self._executor(
                running,
                lambda event: self.store.append_event(run_id, event),
            )
            report = final_report_from_state(state)
            phase = (
                RunPhase.APPROVED
                if report["review"]["status"] == "APPROVED"
                else RunPhase.REVIEW_REQUIRED
            )
            # Deliberately NOT derived from report["changed_files"], which parses the
            # model-authored diff text. The set of paths the apply layer is allowed to
            # write must come only from actual recorded create_file/update_file tool
            # results (the same evidence workspace_changed is derived from) -- never
            # from anything the model merely claims to have changed.
            changed_paths = list(report.get("actual_changed_paths", []))
            self.store.finish(run_id, report, phase, changed_paths=changed_paths)
            workspace = Path(running.workspace_path)
            if running.authorize_writes and phase is RunPhase.APPROVED and changed_paths and all(
                (workspace / path).is_file() for path in changed_paths
            ):
                ApplyService(self.store).apply(
                    run_id, confirmed_project=Path(running.project_path)
                )
        except Exception as exc:  # noqa: BLE001 - every background run must terminate durably.
            self._fail(run_id, exc)

    def _fail(self, run_id: str, exc: Exception) -> None:
        message = redact_secrets(str(exc))
        self.store.append_event(run_id, {
            "id": f"{run_id}-error",
            "name": "workflow error",
            "type": "error",
            "level": "error",
            "status_message": message,
            "metadata": {"code": "WORKFLOW_ERROR"},
            "agent": "human_review",
            "iteration": 0,
            "at": int(time.time() * 1000),
        })
        self.store.finish(
            run_id,
            final_report_from_state(failure_state(run_id, message)),
            RunPhase.FAILED,
        )

    def _execute_real_run(
        self,
        snapshot: RunSnapshot,
        emit: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        sequence = len(snapshot.events)

        def observe(trace_event: dict[str, Any]) -> None:
            nonlocal sequence
            if trace_event.get("name") == "FinalReport":
                return
            sequence += 1
            emit(run_event_from_trace(
                run_id=snapshot.run_id,
                sequence=sequence,
                trace_event=trace_event,
            ))

        state, _trace, _duration, _cloud_first = execute_on_project(
            self.settings,
            project_path=snapshot.workspace_path,
            specification=snapshot.message,
            test_specification=snapshot.test_spec,
            authorize_writes=snapshot.authorize_writes,
            run_id=snapshot.run_id,
            event_observer=observe,
            on_trace_started=lambda trace_id: self.store.record_trace_id(
                snapshot.run_id, trace_id
            ),
        )
        return state


def create_runs_router(
    manager: RunManager | None = None,
    *,
    apply_service: ApplyService | None = None,
) -> APIRouter:
    run_manager = manager or RunManager()
    apply_service = apply_service or ApplyService(run_manager.store)
    router = APIRouter()

    def load_or_404(run_id: str) -> RunSnapshot:
        snapshot = run_manager.get(run_id)
        if snapshot is None:
            raise HTTPException(
                status_code=404,
                detail=_error("RUN_NOT_FOUND", "This run could not be found.", recoverable=False),
            )
        return snapshot

    @router.post("/api/runs", status_code=202)
    def start_run(request: LaunchRequest) -> dict[str, str]:
        if not Path(request.project_path).expanduser().resolve().is_dir():
            raise HTTPException(
                status_code=422,
                detail=_error(
                    "PROJECT_PATH_NOT_FOUND",
                    "The selected project folder could not be found. Choose a valid directory.",
                    recoverable=True,
                ),
            )
        return {"run_id": run_manager.start(request)}

    @router.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        return [summary.model_dump(mode="json") for summary in run_manager.store.list_summaries()]

    @router.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return _public_snapshot(load_or_404(run_id))

    @router.get("/api/runs/{run_id}/events")
    def get_events(run_id: str, after: int = Query(default=0, ge=0)) -> list[dict[str, Any]]:
        load_or_404(run_id)
        return [
            event.model_dump(mode="json")
            for event in run_manager.store.events_after(run_id, after)
        ]

    @router.post("/api/runs/{run_id}/apply")
    def apply_run(run_id: str, request: ApplyRequest) -> dict[str, Any]:
        snapshot = load_or_404(run_id)
        if snapshot.phase not in {RunPhase.APPROVED, RunPhase.APPLIED, RunPhase.APPLY_FAILED}:
            raise HTTPException(
                status_code=409,
                detail=_error(
                    "RUN_NOT_APPROVED",
                    f"This run is not approved for apply (current status: {snapshot.phase.value}).",
                    recoverable=False,
                    phase=snapshot.phase.value,
                ),
            )
        requested = Path(request.project_path).expanduser().resolve()
        if requested != Path(snapshot.project_path).resolve():
            raise HTTPException(
                status_code=409,
                detail=_error(
                    "PROJECT_PATH_MISMATCH",
                    "The confirmed project path does not match this run's project.",
                    recoverable=False,
                ),
            )
        result = apply_service.apply(run_id, confirmed_project=requested)
        return result.model_dump(mode="json")

    @router.post("/api/runs/{run_id}/restore")
    def restore_run(run_id: str, _request: RestoreRequest) -> dict[str, Any]:
        snapshot = load_or_404(run_id)
        already_restored = (
            snapshot.apply_result is not None and snapshot.apply_result.status == "restored"
        )
        no_backup = snapshot.apply_result is None or snapshot.apply_result.backup_path is None
        if snapshot.phase is not RunPhase.APPLY_FAILED and not already_restored:
            raise HTTPException(
                status_code=409,
                detail=_error(
                    "NO_RESTORABLE_BACKUP",
                    "This run has no backup available to restore.",
                    recoverable=False,
                ),
            )
        if not already_restored and no_backup:
            raise HTTPException(
                status_code=409,
                detail=_error(
                    "NO_RESTORABLE_BACKUP",
                    "This run's apply attempt made no changes, so there is nothing to restore.",
                    recoverable=False,
                ),
            )
        result = apply_service.restore(run_id)
        return result.model_dump(mode="json")

    @router.websocket("/ws/runs/{run_id}")
    async def run_events(websocket: WebSocket, run_id: str, after: int = Query(default=0, ge=0)) -> None:
        await websocket.accept()
        snapshot = run_manager.get(run_id)
        if snapshot is None:
            await websocket.send_json({"detail": "run_id not found"})
            await websocket.close(code=4404)
            return

        cursor = after
        last_live_state: tuple[RunPhase, str | None] | None = None
        try:
            while True:
                events = run_manager.store.events_after(run_id, cursor)
                for event in events:
                    await websocket.send_json({"kind": "event", **event.model_dump(mode="json")})
                    cursor = event.sequence
                snapshot = run_manager.store.load(run_id)
                if snapshot.phase not in _ACTIVE_PHASES:
                    final_events = run_manager.store.events_after(run_id, cursor)
                    for event in final_events:
                        await websocket.send_json({
                            "kind": "event",
                            **event.model_dump(mode="json"),
                        })
                        cursor = event.sequence
                    snapshot = run_manager.store.load(run_id)
                    await websocket.send_json({
                        "kind": "snapshot",
                        "snapshot": _public_snapshot(snapshot),
                    })
                    await websocket.close(code=1000)
                    return
                live_state = (snapshot.phase, snapshot.trace_id)
                if live_state != last_live_state:
                    await websocket.send_json({
                        "kind": "snapshot",
                        "snapshot": _public_snapshot(snapshot),
                    })
                    last_live_state = live_state
                await asyncio.to_thread(run_manager.store.wait_after, run_id, cursor, 0.1)
        except WebSocketDisconnect:
            return

    return router


router = create_runs_router()
