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

from engineering_team.contracts.enums import AgentRole, RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.observability.events import RunEventSink

_KNOWN_NODES = {role.value for role in AgentRole}


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

    def _emit(self, *, kind: RunEventKind, agent: str) -> None:
        self._sink.emit(RunEvent(
            event_id=str(uuid.uuid4()), run_id=self._run_id, seq=next(self._seq),
            trace_id=self._trace_id, kind=kind, timestamp=datetime.now(UTC),
            agent=agent, iteration=None, status=None,
            summary=f"{agent} {kind.value.split('_')[-1].lower()}", metrics={},
        ))

    def on_chain_start(
        self, serialized: dict[str, Any], inputs: Any, *,
        run_id: UUID, parent_run_id: UUID | None = None,
        tags: list[str] | None = None, **kwargs: Any,
    ) -> None:
        name = kwargs.get("name")
        if name not in _KNOWN_NODES:
            return
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
