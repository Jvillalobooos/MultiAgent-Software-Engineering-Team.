"""Wraps a TraceSession so every record()/finish() call also emits a RunEvent.

Drop-in replacement for TraceSession wherever code only calls
`.record(...)`, reads `.trace_id`/`.live`, or calls `.finish(...)` —
stategraph.py, llm/runtime.py, and llm/cloud.py all do exactly that, so
none of them need to change to gain event emission.
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.observability.events import RunEventSink
from engineering_team.observability.langfuse import TraceSession

_KIND_BY_AS_TYPE = {
    "generation": RunEventKind.GENERATION,
    "tool": RunEventKind.TOOL,
    "retriever": RunEventKind.RETRIEVER,
    "agent": RunEventKind.AGENT,
}


class EventEmittingTrace:
    def __init__(
        self, *, trace: TraceSession, sink: RunEventSink, run_id: str,
        seq_counter: Iterator[int] | None = None,
    ) -> None:
        self._trace = trace
        self._sink = sink
        self._run_id = run_id
        # Same sharable-counter pattern as RunEventCallbackHandler (Task 4):
        # Task 6 passes one counter to both so every RunEvent for a run —
        # RUN_STARTED, NODE_STARTED/FINISHED, and this class's own
        # GENERATION/TOOL/RETRIEVER/AGENT events — shares one sequence.
        self._seq = seq_counter if seq_counter is not None else itertools.count()

    @property
    def trace_id(self) -> str:
        return self._trace.trace_id

    @property
    def live(self) -> bool:
        return self._trace.live

    def trace_url(self) -> str | None:
        return self._trace.trace_url()

    def record(
        self, name: str, *, as_type: str = "span",
        input: Any | None = None, output: Any | None = None,
        metadata: dict[str, Any] | None = None, level: str | None = None,
        status_message: str | None = None, model: str | None = None,
        usage_details: dict[str, int] | None = None,
    ) -> str:
        observation_id = self._trace.record(
            name, as_type=as_type, input=input, output=output, metadata=metadata,
            level=level, status_message=status_message, model=model,
            usage_details=usage_details,
        )
        safe_metadata = metadata or {}
        self._sink.emit(RunEvent(
            event_id=str(uuid.uuid4()), run_id=self._run_id, seq=next(self._seq),
            trace_id=self._trace.trace_id,
            kind=_KIND_BY_AS_TYPE.get(as_type, RunEventKind.SPAN),
            timestamp=datetime.now(UTC),
            agent=safe_metadata.get("agent"),
            iteration=safe_metadata.get("iteration"),
            status=level or status_message,
            summary=name,
            metrics={"usage": usage_details} if usage_details else {},
            payload={"input": input, "output": output, "metadata": metadata},
        ))
        return observation_id

    def finish(self, final_report: Any) -> None:
        self._trace.finish(final_report)
        self._sink.emit(RunEvent(
            event_id=str(uuid.uuid4()), run_id=self._run_id, seq=next(self._seq),
            trace_id=self._trace.trace_id, kind=RunEventKind.RUN_FINISHED,
            timestamp=datetime.now(UTC), agent=None, iteration=None, status=None,
            summary="run finished", metrics={}, payload={"final_report": final_report},
        ))
