"""Durable data contracts for isolated engineering workflow runs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RunPhase(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    FAILED = "failed"
    APPLYING = "applying"
    APPLIED = "applied"
    APPLY_FAILED = "apply_failed"


class StoredEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sequence: int = Field(ge=1)
    payload: dict[str, Any]


class ApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["applied", "apply_failed", "restored", "conflict"]
    written_paths: list[str] = Field(default_factory=list)
    test_exit_code: int | None = None
    test_output: str = ""
    backup_path: str | None = None
    message: str


class RunSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: str
    project_path: str
    workspace_path: str
    message: str
    test_spec: str | None = None
    authorize_writes: bool = False
    phase: RunPhase
    # The observability trace this run is recorded under. Populated by the executor
    # the moment tracing starts, so the UI can cite a real id instead of a positional
    # "Run #N" label. None only for a run that never reached execution.
    trace_id: str | None = None
    source_hashes: dict[str, str | None]
    events: list[StoredEvent] = Field(default_factory=list)
    report: dict[str, Any] | None = None
    changed_paths: list[str] = Field(default_factory=list)
    apply_result: ApplyResult | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RunSummary(BaseModel):
    """The compact representation used by run-history listings."""

    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: str
    project_path: str
    message: str
    phase: RunPhase
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_snapshot(cls, snapshot: RunSnapshot) -> RunSummary:
        return cls(
            run_id=snapshot.run_id,
            project_path=snapshot.project_path,
            message=snapshot.message,
            phase=snapshot.phase,
            trace_id=snapshot.trace_id,
            created_at=snapshot.created_at,
            updated_at=snapshot.updated_at,
        )
