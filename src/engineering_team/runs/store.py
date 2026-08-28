"""Thread-safe, crash-resilient persistence for workflow run snapshots."""

from __future__ import annotations

import copy
import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engineering_team.runs.models import (
    ApplyResult,
    RunPhase,
    RunSnapshot,
    RunSummary,
    StoredEvent,
)

_ALLOWED_TRANSITIONS: dict[RunPhase, set[RunPhase]] = {
    RunPhase.QUEUED: {RunPhase.PREPARING, RunPhase.FAILED},
    RunPhase.PREPARING: {RunPhase.RUNNING, RunPhase.FAILED},
    RunPhase.RUNNING: {RunPhase.REVIEW_REQUIRED, RunPhase.APPROVED, RunPhase.FAILED},
    RunPhase.REVIEW_REQUIRED: set(),
    RunPhase.APPROVED: {RunPhase.APPLYING},
    RunPhase.FAILED: set(),
    # APPLYING -> APPROVED covers a conflict revert: detected before any source
    # file was written, so the run is safe to hand back for a fresh apply attempt.
    RunPhase.APPLYING: {RunPhase.APPLIED, RunPhase.APPLY_FAILED, RunPhase.APPROVED},
    RunPhase.APPLIED: set(),
    RunPhase.APPLY_FAILED: {RunPhase.APPROVED},
}

_FINISH_PHASES = {RunPhase.REVIEW_REQUIRED, RunPhase.APPROVED, RunPhase.FAILED}


class RunStore:
    """Persist run snapshots under ``<root>/_records`` with atomic replacement."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.records_root = self.root / "_records"
        self.records_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._snapshots: dict[str, RunSnapshot] = {}
        self._load_existing()

    def create(self, snapshot: RunSnapshot) -> RunSnapshot:
        """Create and persist a new run snapshot."""
        with self._condition:
            self._record_path(snapshot.run_id)
            if snapshot.run_id in self._snapshots:
                raise ValueError(f"run already exists: {snapshot.run_id}")
            stored = snapshot.model_copy(deep=True)
            self._persist(stored)
            self._snapshots[stored.run_id] = stored
            self._condition.notify_all()
            return stored.model_copy(deep=True)

    def load(self, run_id: str) -> RunSnapshot:
        """Return an independent copy of a persisted run snapshot."""
        with self._lock:
            return self._snapshot(run_id).model_copy(deep=True)

    def list_summaries(self) -> list[RunSummary]:
        with self._lock:
            snapshots = sorted(
                self._snapshots.values(),
                key=lambda item: (item.updated_at, item.run_id),
                reverse=True,
            )
            return [RunSummary.from_snapshot(item) for item in snapshots]

    def transition(self, run_id: str, phase: RunPhase) -> RunSnapshot:
        """Move a run through one explicitly allowed state transition."""
        with self._condition:
            snapshot = self._candidate(run_id)
            self._validate_transition(snapshot, phase)
            snapshot.phase = phase
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def append_event(self, run_id: str, event: dict[str, Any]) -> StoredEvent:
        """Append an event, assigning its next durable sequence number."""
        with self._condition:
            snapshot = self._candidate(run_id)
            sequence = snapshot.events[-1].sequence + 1 if snapshot.events else 1
            stored = StoredEvent(sequence=sequence, payload=copy.deepcopy(event))
            snapshot.events.append(stored)
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return stored.model_copy(deep=True)

    def record_source_hashes(self, run_id: str, hashes: dict[str, str | None]) -> RunSnapshot:
        """Persist the computed source baseline hashes for an existing run."""
        with self._condition:
            snapshot = self._candidate(run_id)
            snapshot.source_hashes = copy.deepcopy(hashes)
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def record_trace_id(self, run_id: str, trace_id: str) -> RunSnapshot:
        """Persist the observability trace id as soon as tracing starts.

        Written once, at the beginning of execution, so a live run can be cited by
        its real trace id rather than by its position in a list.
        """
        with self._condition:
            snapshot = self._candidate(run_id)
            snapshot.trace_id = trace_id
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def record_apply_result(self, run_id: str, result: ApplyResult) -> RunSnapshot:
        """Persist an apply or restore audit record for an existing run."""
        with self._condition:
            snapshot = self._candidate(run_id)
            snapshot.apply_result = result.model_copy(deep=True)
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def update_report(self, run_id: str, **updates: object) -> RunSnapshot:
        """Persist post-workflow facts such as an automatic source apply."""
        with self._condition:
            snapshot = self._candidate(run_id)
            snapshot.report = {**(snapshot.report or {}), **updates}
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def complete_apply(self, run_id: str, result: ApplyResult) -> RunSnapshot:
        """Atomically expose a successful source write and its audit record."""
        with self._condition:
            snapshot = self._candidate(run_id)
            self._validate_transition(snapshot, RunPhase.APPLIED)
            snapshot.apply_result = result.model_copy(deep=True)
            snapshot.phase = RunPhase.APPLIED
            snapshot.report = {**(snapshot.report or {}), "source_applied": True}
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def events_after(self, run_id: str, sequence: int) -> list[StoredEvent]:
        """Return all durable events with a sequence strictly above ``sequence``."""
        with self._lock:
            return self._events_after(run_id, sequence)

    def finish(
        self,
        run_id: str,
        report: dict[str, Any],
        phase: RunPhase,
        *,
        changed_paths: list[str] | None = None,
    ) -> RunSnapshot:
        """Atomically persist a terminal workflow report and phase."""
        if phase not in _FINISH_PHASES:
            raise ValueError(f"finish phase must be terminal workflow phase, got {phase.value}")
        with self._condition:
            snapshot = self._candidate(run_id)
            self._validate_transition(snapshot, phase)
            snapshot.report = copy.deepcopy(report)
            snapshot.phase = phase
            if changed_paths is not None:
                snapshot.changed_paths = list(changed_paths)
            snapshot.updated_at = datetime.now(UTC)
            self._commit(snapshot)
            self._condition.notify_all()
            return snapshot.model_copy(deep=True)

    def wait_after(self, run_id: str, sequence: int, timeout: float | None) -> list[StoredEvent]:
        """Wait until at least one event after ``sequence`` is available or time expires."""
        with self._condition:
            self._snapshot(run_id)
            self._condition.wait_for(
                lambda: bool(self._events_after(run_id, sequence)), timeout=timeout,
            )
            return self._events_after(run_id, sequence)

    def _load_existing(self) -> None:
        for record in self.records_root.glob("*.json"):
            snapshot = RunSnapshot.model_validate_json(record.read_text(encoding="utf-8"))
            self._record_path(snapshot.run_id)
            if snapshot.run_id in self._snapshots:
                raise ValueError(f"duplicate persisted run: {snapshot.run_id}")
            self._snapshots[snapshot.run_id] = snapshot

    def _snapshot(self, run_id: str) -> RunSnapshot:
        try:
            return self._snapshots[run_id]
        except KeyError as exc:
            raise KeyError(f"run not found: {run_id}") from exc

    def _candidate(self, run_id: str) -> RunSnapshot:
        return self._snapshot(run_id).model_copy(deep=True)

    def _commit(self, snapshot: RunSnapshot) -> None:
        self._persist(snapshot)
        self._snapshots[snapshot.run_id] = snapshot

    def _record_path(self, run_id: str) -> Path:
        candidate = Path(run_id)
        if not run_id or candidate.name != run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be a single file name")
        return self.records_root / f"{run_id}.json"

    def _persist(self, snapshot: RunSnapshot) -> None:
        path = self._record_path(snapshot.run_id)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        serialized = json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(serialized)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _events_after(self, run_id: str, sequence: int) -> list[StoredEvent]:
        snapshot = self._snapshot(run_id)
        return [event.model_copy(deep=True) for event in snapshot.events if event.sequence > sequence]

    @staticmethod
    def _validate_transition(snapshot: RunSnapshot, phase: RunPhase) -> None:
        if phase not in _ALLOWED_TRANSITIONS[snapshot.phase]:
            raise ValueError(f"invalid run phase transition: {snapshot.phase.value} -> {phase.value}")
        if (
            snapshot.phase is RunPhase.APPLY_FAILED
            and phase is RunPhase.APPROVED
            and (snapshot.apply_result is None or snapshot.apply_result.status != "restored")
        ):
            raise ValueError("invalid run phase transition: apply_failed -> approved requires restored audit")
