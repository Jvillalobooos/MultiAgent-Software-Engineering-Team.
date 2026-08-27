"""Turns LangGraph node execution into explicit RunEvent(s).

LangGraph fires on_chain_start/on_chain_end once per node via the standard
LangChain callback protocol, each pair sharing one run_id (LangChain's own,
unrelated to our run_id). This is the one place node start/finish is
observed — nothing else in the graph records it explicitly.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.observability.events import RunEventSink


class RunEventCallbackHandler(BaseCallbackHandler):
    def __init__(
        self, *, sink: RunEventSink, run_id: str, trace_id: str | None = None,
        seq_counter: Iterator[int] | None = None,
    ) -> None:
        self._sink = sink
        self._run_id = run_id
        self._trace_id = trace_id
        # Accepts a shared counter so a caller emitting its own RUN_STARTED/
        # RUN_FINISHED events (Task 6) can keep one monotonic seq across all
        # of them; standalone use (this task's own tests) falls back to a
        # fresh counter starting at 0.
        self._seq = seq_counter if seq_counter is not None else itertools.count()
        self._active: dict[UUID, str] = {}
        # The outermost "LangGraph" wrapper call has parent_run_id=None; every
        # real graph node's parent_run_id equals THAT run's run_id. Internal
        # LangChain machinery (RunnableCallable wrappers, conditional-edge
        # functions like "developer_next") is parented to a *node's* run_id
        # instead, one level deeper — so filtering on "parent equals the root
        # run_id" (verified empirically against build_walking_graph() and
        # build_engineering_graph()) picks out exactly the real named nodes,
        # without hardcoding a node-name allowlist that misses nodes like
        # "FinalReport"/"HUMAN_REVIEW_REQUIRED"/"security_hitl".
        self._root_run_id: UUID | None = None

    def _emit(self, *, kind: RunEventKind, agent: str, status: str | None = None) -> None:
        self._sink.emit(RunEvent(
            event_id=str(uuid.uuid4()), run_id=self._run_id, seq=next(self._seq),
            trace_id=self._trace_id, kind=kind, timestamp=datetime.now(UTC),
            agent=agent, iteration=None, status=status,
            summary=f"{agent} {kind.value.split('_')[-1].lower()}", metrics={},
        ))

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: Any, *,
        run_id: UUID, parent_run_id: UUID | None = None,
        tags: list[str] | None = None, **kwargs: Any,
    ) -> None:
        if parent_run_id is None:
            # This is the outermost "LangGraph" wrapper run itself.
            self._root_run_id = run_id
            return
        if parent_run_id != self._root_run_id:
            return
        name = kwargs.get("name") or "unknown"
        self._active[run_id] = name
        self._emit(kind=RunEventKind.NODE_STARTED, agent=name)

    def on_chain_end(
        self, outputs: Any, *,
        run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any,
    ) -> None:
        name = self._active.pop(run_id, None)
        if name is None:
            return
        self._emit(kind=RunEventKind.NODE_FINISHED, agent=name)

    def on_chain_error(
        self, error: BaseException, *,
        run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any,
    ) -> None:
        name = self._active.pop(run_id, None)
        if name is None:
            return
        self._emit(kind=RunEventKind.NODE_FINISHED, agent=name, status="ERROR")
