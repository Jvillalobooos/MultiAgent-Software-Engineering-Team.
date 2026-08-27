# Ejecución aislada y eventos (Fase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `run_on_project` (and, later, a FastAPI layer) a structured, real-time stream of `RunEvent`s for every workflow run, driven directly from LangGraph/Langfuse instrumentation — never inferred by polling Langfuse — with zero behavior change to the existing `run-project` CLI when no sink is supplied.

**Architecture:** A single `TraceSession.record(...)` call already fires at every meaningful point in the graph (RAG retrieval, MCP tool call, model call, node output, errors, HITL) — see `graph/stategraph.py`. Instead of touching each of those ~15 call sites, `EventEmittingTrace` wraps a `TraceSession` behind the exact same `record()`/`trace_id` surface stategraph.py already depends on, so it drops in as `trace=` with **no changes to `stategraph.py`, `llm/runtime.py`, `llm/cloud.py`, or `mcp/repository.py`**. Node-level start/finish — which nothing today records explicitly — comes from a `RunEventCallbackHandler` (a LangChain `BaseCallbackHandler`) passed via `config={"callbacks": [...]}` to `graph.invoke()`; LangGraph fires `on_chain_start`/`on_chain_end` per node with the node's own name, verified empirically against this repo's real graph (see Task 4). This is the LangGraph-native mechanism for "eventos explícitos de inicio/fin sin inferir desde Langfuse" — an outer `graph.stream()` loop only yields *after* a node finishes, giving no true start signal, so callbacks are used instead of `.stream()` here. Incremental HTTP delivery via `graph.stream()` is a Phase 2/3 (API layer) concern, not this phase's.

**Tech Stack:** Python 3.11+, Pydantic (StrictModel), LangGraph (`langchain_core.callbacks.BaseCallbackHandler`), pytest.

**Spec:** [docs/superpowers/specs/2026-08-27-backend-frontend-integration-design.md](../specs/2026-08-27-backend-frontend-integration-design.md) — sections 2 (`RunEventV1`), 3.1, 7.1.

## Global Constraints

- `schema_version` on every `RunEvent` starts at `1` (spec §2).
- `RunEventV1` fields per spec §2: `schema_version, event_id, run_id, seq, trace_id, kind, timestamp, agent, iteration, status, summary, metrics, payload_ref`. This phase also carries the full redacted payload inline as `payload` (no external payload store exists yet — Phase 2 introduces one and will populate `payload_ref` from it; `payload` stays as an internal transitional field, documented here so it is not mistaken for scope creep).
- No inferring run/node state by querying Langfuse (spec §1, §3.1) — every event in this phase is produced synchronously from the same process running the graph.
- `run_on_project`'s existing public return-value shape and the `run-project` CLI's behavior are unchanged when `event_sink` is not supplied (spec §3.1 "conservando el comportamiento público del CLI").
- Secrets redaction: reuse `engineering_team.guardrails.secrets.redact_secrets` / the existing `_safe()` helper in `observability/langfuse.py` — never construct a second redaction path.
- FastAPI, SQLite, Kafka, the frontend, and Apply are out of scope for this phase (spec §7, phases 2-4).

---

### Task 1: `RunEventKind` enum and `RunEvent` contract

**Files:**
- Modify: `src/engineering_team/contracts/enums.py` (append `RunEventKind`)
- Modify: `src/engineering_team/contracts/models.py` (append `RunEvent`)
- Test: `tests/unit/test_run_events.py`

**Interfaces:**
- Produces: `RunEventKind` (StrEnum: `RUN_STARTED, NODE_STARTED, NODE_FINISHED, GENERATION, TOOL, RETRIEVER, AGENT, SPAN, RUN_FINISHED`) and `RunEvent` (`StrictModel`) for every later task in this plan.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_run_events.py
import pytest
from pydantic import ValidationError

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent


def test_run_event_requires_schema_version_one_by_default():
    event = RunEvent(
        event_id="e1", run_id="run-1", seq=0, trace_id="t1",
        kind=RunEventKind.RUN_STARTED, agent=None, iteration=None,
        status=None, summary="run started", metrics={},
    )
    assert event.schema_version == 1
    assert event.payload_ref is None
    assert event.payload is None


def test_run_event_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RunEvent(
            event_id="e1", run_id="run-1", seq=0, trace_id="t1",
            kind=RunEventKind.RUN_STARTED, agent=None, iteration=None,
            status=None, summary="x", metrics={}, unexpected="nope",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_run_events.py -v`
Expected: FAIL with `ImportError: cannot import name 'RunEventKind'` (enum doesn't exist yet).

- [ ] **Step 3: Add `RunEventKind` to `contracts/enums.py`**

Append at the end of `src/engineering_team/contracts/enums.py`:

```python
class RunEventKind(StrEnum):
    RUN_STARTED = "RUN_STARTED"
    NODE_STARTED = "NODE_STARTED"
    NODE_FINISHED = "NODE_FINISHED"
    GENERATION = "GENERATION"
    TOOL = "TOOL"
    RETRIEVER = "RETRIEVER"
    AGENT = "AGENT"
    SPAN = "SPAN"
    RUN_FINISHED = "RUN_FINISHED"
```

- [ ] **Step 4: Add `RunEvent` to `contracts/models.py`**

Add the import at the top of `src/engineering_team/contracts/models.py` (extend the existing `from .enums import (...)` block with `RunEventKind`), then append the model at the end of the file:

```python
class RunEvent(StrictModel):
    schema_version: int = 1
    event_id: str
    run_id: str
    seq: int = Field(ge=0)
    trace_id: str | None = None
    kind: RunEventKind
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent: str | None = None
    iteration: int | None = None
    status: str | None = None
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] | None = None
    payload_ref: str | None = None
```

`datetime`, `timezone`, and `Any` are already imported at the top of `contracts/models.py` (used by `WorkflowError.occurred_at` and `RetrievedEvidence.retrieved_at`) — no new imports needed beyond adding `RunEventKind` to the `.enums` import.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_run_events.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add src/engineering_team/contracts/enums.py src/engineering_team/contracts/models.py tests/unit/test_run_events.py
git commit -m "feat: add RunEvent contract and RunEventKind"
```

---

### Task 2: `RunEventSink` protocol and two implementations

**Files:**
- Create: `src/engineering_team/observability/events.py`
- Test: `tests/unit/test_run_events.py` (extend)

**Interfaces:**
- Consumes: `RunEvent` (Task 1).
- Produces: `RunEventSink` (Protocol with `emit(event: RunEvent) -> None`), `NullRunEventSink`, `ListRunEventSink` (`.events: list[RunEvent]`) — used by every later task.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_run_events.py`:

```python
from engineering_team.observability.events import ListRunEventSink, NullRunEventSink


def _event(seq: int) -> RunEvent:
    return RunEvent(
        event_id=f"e{seq}", run_id="run-1", seq=seq, trace_id="t1",
        kind=RunEventKind.RUN_STARTED, agent=None, iteration=None,
        status=None, summary="x", metrics={},
    )


def test_null_sink_accepts_and_discards_events():
    sink = NullRunEventSink()
    sink.emit(_event(0))  # must not raise


def test_list_sink_preserves_emission_order():
    sink = ListRunEventSink()
    sink.emit(_event(0))
    sink.emit(_event(1))
    assert [event.seq for event in sink.events] == [0, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_run_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.observability.events'`

- [ ] **Step 3: Write the implementation**

```python
# src/engineering_team/observability/events.py
"""Sinks that receive RunEvents as a workflow run executes.

A sink never blocks or fails the run: implementations that talk to an
external system (Kafka in Phase 2) are expected to catch their own errors.
"""

from __future__ import annotations

from typing import Protocol

from engineering_team.contracts.models import RunEvent


class RunEventSink(Protocol):
    def emit(self, event: RunEvent) -> None: ...


class NullRunEventSink:
    """Default sink: discards every event. Used when no caller wants one."""

    def emit(self, event: RunEvent) -> None:
        return None


class ListRunEventSink:
    """In-memory sink for tests and for a single synchronous CLI run."""

    def __init__(self) -> None:
        self.events: list[RunEvent] = []

    def emit(self, event: RunEvent) -> None:
        self.events.append(event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_run_events.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/observability/events.py tests/unit/test_run_events.py
git commit -m "feat: add RunEventSink protocol with null and in-memory implementations"
```

---

### Task 3: `TraceSession.trace_url()`

**Files:**
- Modify: `src/engineering_team/observability/langfuse.py:34-107` (the `TraceSession` dataclass)
- Test: `tests/unit/test_observability_langfuse.py` (create if it does not already cover this; otherwise extend the existing Langfuse test file — check `tests/integration/test_observability.py` first and add there if that is where `TraceSession` is already tested)

**Interfaces:**
- Consumes: `TraceSession.client` (already a field — the raw `Langfuse` SDK client when live), `TraceSession.trace_id`, `TraceSession.root` (already fields).
- Produces: `TraceSession.trace_url() -> str | None`, used by Task 5's `RunEvent` payload for `RUN_FINISHED`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/integration/test_observability.py
from unittest.mock import MagicMock

from engineering_team.observability.langfuse import TraceSession


def test_trace_url_is_none_when_offline():
    session = TraceSession(trace_id="t1", run_id="run-1", live=False)
    assert session.trace_url() is None


def test_trace_url_delegates_to_the_live_client():
    client = MagicMock()
    client.get_trace_url.return_value = "https://cloud.langfuse.com/project/p1/traces/t1"
    session = TraceSession(trace_id="t1", run_id="run-1", live=True, client=client)

    assert session.trace_url() == "https://cloud.langfuse.com/project/p1/traces/t1"
    client.get_trace_url.assert_called_once_with(trace_id="t1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_observability.py -k trace_url -v`
Expected: FAIL with `AttributeError: 'TraceSession' object has no attribute 'trace_url'`

- [ ] **Step 3: Add the method**

In `src/engineering_team/observability/langfuse.py`, add this method to the `TraceSession` dataclass, right after `record` (before `finish`, i.e. after line 87 `return span.id`):

```python
    def trace_url(self) -> str | None:
        if self.client is None or not hasattr(self.client, "get_trace_url"):
            return None
        return self.client.get_trace_url(trace_id=self.trace_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/test_observability.py -k trace_url -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/observability/langfuse.py tests/integration/test_observability.py
git commit -m "feat: add TraceSession.trace_url()"
```

---

### Task 4: `RunEventCallbackHandler` — node start/finish from LangGraph callbacks

**Files:**
- Create: `src/engineering_team/observability/event_callbacks.py`
- Test: `tests/unit/test_event_callbacks.py`

**Interfaces:**
- Consumes: `RunEventSink`, `RunEvent`, `RunEventKind` (Tasks 1-2); `AgentRole` (`contracts.enums`, existing).
- Produces: `RunEventCallbackHandler(sink, run_id, trace_id=None)`, a `langchain_core.callbacks.BaseCallbackHandler` subclass, passed as `config={"callbacks": [handler]}` to `graph.invoke(...)` (wired in Task 5).

This task's behavior was verified interactively against this repo's real `build_walking_graph()` graph before writing this plan: `on_chain_start` fires once per node with `kwargs["name"]` equal to the node's registered name (`"Product"`, `"Architecture"`, ...) and a unique `run_id` per node invocation (LangChain's own run id, unrelated to our `run_id`); `on_chain_end` fires with the *same* `run_id`, letting a `run_id -> node name` map correlate start/end. The outer `"LangGraph"` wrapper node (and any other name not in `AgentRole`) must be filtered out.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_event_callbacks.py
from engineering_team.contracts.enums import RunEventKind
from engineering_team.graph.stategraph import build_walking_graph
from engineering_team.observability.event_callbacks import RunEventCallbackHandler
from engineering_team.observability.events import ListRunEventSink


def test_callback_handler_emits_node_started_and_finished_in_order():
    sink = ListRunEventSink()
    handler = RunEventCallbackHandler(sink=sink, run_id="run-1")
    graph = build_walking_graph()

    graph.invoke({"visited": []}, config={"callbacks": [handler]})

    kinds_and_agents = [(event.kind, event.agent) for event in sink.events]
    assert kinds_and_agents == [
        (RunEventKind.NODE_STARTED, "Product"), (RunEventKind.NODE_FINISHED, "Product"),
        (RunEventKind.NODE_STARTED, "Architecture"), (RunEventKind.NODE_FINISHED, "Architecture"),
        (RunEventKind.NODE_STARTED, "Developer"), (RunEventKind.NODE_FINISHED, "Developer"),
        (RunEventKind.NODE_STARTED, "Security"), (RunEventKind.NODE_FINISHED, "Security"),
        (RunEventKind.NODE_STARTED, "Testing"), (RunEventKind.NODE_FINISHED, "Testing"),
        (RunEventKind.NODE_STARTED, "Reviewer"), (RunEventKind.NODE_FINISHED, "Reviewer"),
    ]
    assert [event.seq for event in sink.events] == list(range(12))


def test_callback_handler_ignores_the_outer_graph_wrapper_node():
    sink = ListRunEventSink()
    handler = RunEventCallbackHandler(sink=sink, run_id="run-1")
    graph = build_walking_graph()

    graph.invoke({"visited": []}, config={"callbacks": [handler]})

    assert all(event.agent != "LangGraph" for event in sink.events)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_event_callbacks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.observability.event_callbacks'`

- [ ] **Step 3: Write the implementation**

```python
# src/engineering_team/observability/event_callbacks.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_event_callbacks.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/observability/event_callbacks.py tests/unit/test_event_callbacks.py
git commit -m "feat: emit NODE_STARTED/NODE_FINISHED from LangGraph callbacks"
```

---

### Task 5: `EventEmittingTrace` — drop-in wrapper around `TraceSession`

**Files:**
- Create: `src/engineering_team/observability/event_trace.py`
- Test: `tests/unit/test_event_trace.py`

**Interfaces:**
- Consumes: `TraceSession` (existing, `observability.langfuse`), `RunEventSink`/`RunEvent`/`RunEventKind` (Tasks 1-2).
- Produces: `EventEmittingTrace(trace, sink, run_id)`, exposing `.trace_id` (property), `.live` (property), `.record(...)` (same signature as `TraceSession.record`), `.finish(final_report)`, `.trace_url()` — this is what Task 6 passes as `trace=` to `build_engineering_graph(...)`, `LocalModelRuntime(...)`, `CloudModelRuntime(...)` in place of a raw `TraceSession`, since `stategraph.py`/`llm/runtime.py`/`llm/cloud.py` only ever call `trace.record(...)` / read `trace.trace_id` — see the constructor calls at `apply_run.py:68-76,80-84,102`.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_event_trace.py
from engineering_team.contracts.enums import RunEventKind
from engineering_team.observability.event_trace import EventEmittingTrace
from engineering_team.observability.events import ListRunEventSink
from engineering_team.observability.langfuse import TraceSession


def test_record_forwards_to_the_wrapped_trace_and_emits_an_event():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    observation_id = wrapped.record(
        "Security", as_type="agent", output={"status": "PASS"},
        metadata={"agent": "Security", "iteration": 1},
    )

    assert observation_id == "local-1"
    assert trace.events[0]["name"] == "Security"  # the wrapped TraceSession really recorded it
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.kind == RunEventKind.AGENT
    assert event.agent == "Security"
    assert event.iteration == 1
    assert event.summary == "Security"
    assert event.payload == {"input": None, "output": {"status": "PASS"}, "metadata": {"agent": "Security", "iteration": 1}}


def test_trace_id_and_live_are_passed_through():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=True)
    wrapped = EventEmittingTrace(trace=trace, sink=ListRunEventSink(), run_id="run-1")

    assert wrapped.trace_id == "t1"
    assert wrapped.live is True


def test_finish_emits_a_run_finished_event():
    trace = TraceSession(trace_id="t1", run_id="run-1", live=False)
    sink = ListRunEventSink()
    wrapped = EventEmittingTrace(trace=trace, sink=sink, run_id="run-1")

    wrapped.finish({"status": "APPROVED"})

    assert trace.finished is True
    assert sink.events[-1].kind == RunEventKind.RUN_FINISHED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_event_trace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engineering_team.observability.event_trace'`

- [ ] **Step 3: Write the implementation**

```python
# src/engineering_team/observability/event_trace.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_event_trace.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/engineering_team/observability/event_trace.py tests/unit/test_event_trace.py
git commit -m "feat: add EventEmittingTrace wrapper"
```

---

### Task 6: Wire `event_sink` into `run_on_project` end-to-end

**Files:**
- Modify: `src/engineering_team/apply_run.py:41-112` (`run_on_project`)
- Test: `tests/integration/test_run_events_integration.py`

**Interfaces:**
- Consumes: `EventEmittingTrace` (Task 5), `RunEventCallbackHandler` (Task 4), `RunEventSink`/`NullRunEventSink`/`ListRunEventSink` (Task 2), `RunEvent`/`RunEventKind` (Task 1).
- Produces: `run_on_project(..., event_sink: RunEventSink | None = None)` — new keyword-only parameter, default `None` (behaves exactly as before: an internal `NullRunEventSink()` is used, so nothing observable changes for the existing CLI).

- [ ] **Step 1: Write the failing test**

This test exercises the graph the same deterministic way `tests/integration/test_workflow.py` already does (no retriever/MCP/model_runtime — `build_engineering_graph` defaults every optional collaborator to `None` and the agents' own deterministic `.execute()` output becomes the node's result). It calls `run_on_project`'s internals directly rather than the full function, because `run_on_project` always builds a real `MCPRepositoryClient`/`MCPQualityClient` over stdio and a real RAG retriever — exercising the *full* function against a real project belongs in a live/manual check (see `docs/apply-run-example.md`), not this fast unit-style test. Instead, this test imports `_run_graph_with_events`, the small helper Step 3 extracts from the middle of `run_on_project` specifically so it's independently testable.

```python
# tests/integration/test_run_events_integration.py
from engineering_team.apply_run import _run_graph_with_events
from engineering_team.contracts.enums import RunEventKind
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.events import ListRunEventSink


def test_full_run_emits_run_started_node_events_and_run_finished_in_order():
    sink = ListRunEventSink()
    graph = build_engineering_graph()

    state = _run_graph_with_events(
        graph,
        {"run_id": "run-1", "requirement": "safe bounded change"},
        run_id="run-1", trace=None, sink=sink,
    )

    assert state["final_status"] == "APPROVED"
    kinds = [event.kind for event in sink.events]
    assert kinds[0] == RunEventKind.RUN_STARTED
    assert kinds[-1] == RunEventKind.RUN_FINISHED
    assert kinds.count(RunEventKind.NODE_STARTED) == 6  # Product..Reviewer, no rejection cycle
    assert kinds.count(RunEventKind.NODE_FINISHED) == 6
    assert [event.seq for event in sink.events] == list(range(len(sink.events)))


def test_event_sink_defaults_to_a_null_sink_when_not_provided():
    graph = build_engineering_graph()
    # No sink argument at all — must not raise, must behave like today.
    state = _run_graph_with_events(
        graph, {"run_id": "run-2", "requirement": "safe bounded change"},
        run_id="run-2", trace=None,
    )
    assert state["final_status"] == "APPROVED"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/integration/test_run_events_integration.py -v`
Expected: FAIL with `ImportError: cannot import name '_run_graph_with_events'`

- [ ] **Step 3: Extract `_run_graph_with_events` and wire it into `run_on_project`**

In `src/engineering_team/apply_run.py`, add these imports alongside the existing ones at the top (`itertools` joins the existing `json`/`time`/`uuid` stdlib imports):

```python
import itertools

from engineering_team.contracts.enums import RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.observability.event_callbacks import RunEventCallbackHandler
from engineering_team.observability.event_trace import EventEmittingTrace
from engineering_team.observability.events import NullRunEventSink, RunEventSink
```

Add this new function right after `_default_test_paths` (before `def run_on_project`):

```python
def _run_graph_with_events(
    graph: Any,
    initial_state: dict[str, Any],
    *,
    run_id: str,
    trace: Any | None,
    sink: RunEventSink | None = None,
    seq_counter: Any | None = None,
) -> dict[str, Any]:
    """Invoke a compiled graph, emitting RUN_STARTED/RUN_FINISHED and, via
    RunEventCallbackHandler, NODE_STARTED/NODE_FINISHED for every node.

    ``seq_counter``, when supplied, is the same counter passed to the
    ``EventEmittingTrace`` wrapping ``trace`` (Task 5), so RUN_STARTED,
    every NODE_STARTED/FINISHED, and every GENERATION/TOOL/RETRIEVER/AGENT
    event recorded during the run share one strictly increasing sequence.
    Falls back to a fresh counter when not supplied (this task's own tests,
    which use ``trace=None`` and never construct an ``EventEmittingTrace``).
    """
    active_sink = sink or NullRunEventSink()
    trace_id = getattr(trace, "trace_id", None)
    active_seq = seq_counter if seq_counter is not None else itertools.count()
    active_sink.emit(RunEvent(
        event_id=str(uuid.uuid4()), run_id=run_id, seq=next(active_seq), trace_id=trace_id,
        kind=RunEventKind.RUN_STARTED, agent=None, iteration=None, status=None,
        summary="run started", metrics={},
    ))
    handler = RunEventCallbackHandler(
        sink=active_sink, run_id=run_id, trace_id=trace_id, seq_counter=active_seq,
    )
    state = graph.invoke(initial_state, config={"callbacks": [handler]})
    active_sink.emit(RunEvent(
        event_id=str(uuid.uuid4()), run_id=run_id, seq=next(active_seq), trace_id=trace_id,
        kind=RunEventKind.RUN_FINISHED, agent=None, iteration=None,
        status=state.get("final_status"), summary="run finished", metrics={},
    ))
    return state
```

Now replace `run_on_project` in full (everything from `def run_on_project(` through the end of the `with (...)` block that currently ends at `.invoke({...})`) with:

```python
def run_on_project(
    settings: Settings,
    *,
    project_path: str | Path,
    specification: str,
    test_specification: str | None = None,
    authorize_writes: bool = False,
    test_paths: list[str] | None = None,
    report_path: str | Path | None = None,
    event_sink: RunEventSink | None = None,
) -> dict[str, Any]:
    """Run Product→...→Reviewer against ``project_path`` and, if authorized, apply changes.

    ``authorize_writes`` is the explicit human authorization the destructive-change
    guardrail requires (``guardrails.validation.require_explicit_destructive_authorization``)
    — without it the Developer still produces a full ``ImplementationResult`` with
    LLM-authored ``file_contents``, but nothing is written to disk and the run is
    routed to human review instead.

    ``event_sink``, when supplied, receives a ``RunEvent`` for every RAG
    retrieval, MCP tool call, model call, node start/finish, and the run's
    own start/finish — see ``observability/events.py``. When ``None``
    (the default), behavior is identical to before this parameter existed.
    """
    project_root = Path(project_path).resolve()
    if not project_root.is_dir():
        raise ValueError(f"project path does not exist or is not a directory: {project_root}")

    requirement = specification.strip()
    if test_specification and test_specification.strip():
        requirement = f"{requirement}\n\nTest specification: {test_specification.strip()}"

    run_id = f"apply-{uuid.uuid4()}"
    trace = LangfuseTracer(
        public_key=settings.langfuse_public_key,
        secret_key=(
            settings.langfuse_secret_key.get_secret_value()
            if settings.langfuse_secret_key else None
        ),
        base_url=settings.langfuse_base_url,
        offline_directory="evaluation/reports/traces",
    ).start_run(run_id, requirement)

    seq_counter = itertools.count()
    event_trace: Any = (
        EventEmittingTrace(trace=trace, sink=event_sink, run_id=run_id, seq_counter=seq_counter)
        if event_sink is not None else trace
    )

    cloud_first = bool(settings.cloud_enabled and not settings.local_first)
    if cloud_first:
        primary_runtime: Any = CloudModelRuntime(settings, trace=event_trace, primary=True)
        secondary_runtime: Any | None = LocalModelRuntime(settings, trace=event_trace)
    else:
        primary_runtime = LocalModelRuntime(settings, trace=event_trace)
        secondary_runtime = CloudModelRuntime(settings, trace=event_trace) if settings.cloud_enabled else None

    retriever = build_retriever(settings, settings.rag_persist_directory, reindex=True)
    resolved_test_paths = test_paths or _default_test_paths(
        DeveloperAgent.requested_targets(requirement)
    )

    started = time.perf_counter()
    with (
        MCPRepositoryClient(project_root, timeout_seconds=120) as repository_mcp,
        MCPQualityClient(project_root, timeout_seconds=120) as quality_mcp,
    ):
        graph = build_engineering_graph(
            repository_mcp=repository_mcp,
            quality_mcp=quality_mcp,
            retriever=retriever,
            model_runtime=primary_runtime,
            cloud_runtime=secondary_runtime,
            trace=event_trace,
            test_paths=resolved_test_paths,
        )
        state = _run_graph_with_events(
            graph,
            {
                "run_id": run_id,
                "requirement": requirement,
                "repository_context": {
                    "apply_changes": True,
                    "authorized": authorize_writes,
                    "project_path": str(project_root),
                },
            },
            run_id=run_id, trace=event_trace, sink=event_sink, seq_counter=seq_counter,
        )
    duration = time.perf_counter() - started
```

Everything from `implementation = state.get("implementation")` to the end of the function (the `evidence` dict and `report_path` write) is unchanged — only the part above it (up to and including `duration = time.perf_counter() - started`) is replaced.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/integration/test_run_events_integration.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full existing suite to confirm no regression**

Run: `.venv/bin/python -m pytest -q --deselect tests/e2e/test_multimodel_evidence.py::test_one_normal_run_invokes_both_local_models_through_router`
Expected: all pass, same count as before plus this plan's new tests.

Run: `.venv/bin/python -m ruff check src/ tests/`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add src/engineering_team/apply_run.py tests/integration/test_run_events_integration.py
git commit -m "feat: wire RunEventSink through run_on_project"
```

---

### Task 7: Isolated API workspace with fingerprint + hashes

**Files:**
- Modify: `src/engineering_team/workspace/isolation.py` (append a new function; `create_run_copy` and its imports stay untouched)
- Test: `tests/unit/test_api_workspace.py`

**Interfaces:**
- Consumes: `resolve_inside` (existing, `workspace/paths.py`).
- Produces: `WorkspaceFingerprint` (`@dataclass`: `workspace_path: Path`, `source_path: Path`, `file_hashes: dict[str, str]` — relative POSIX path to sha256 hex digest) and `create_api_workspace(run_id: str, source: str | Path, workspace_root: str | Path) -> WorkspaceFingerprint`. This is the "executor para la API que copie el proyecto" from spec §3.1 — a future FastAPI layer (Phase 2) calls this once per run before invoking the graph; it is not wired into `run_on_project`/the CLI in this phase, since the CLI already runs directly against the caller's project path by design (`apply_run.py`'s docstring).

`create_run_copy` (existing, used by the evaluation harness to copy `sample_app`) stays as-is — it is tuned for this repo's own bundled demo app. `create_api_workspace` is deliberately separate because it must reject two things `create_run_copy` does not need to: `.env`/`.env.*` files (this repo already treats those as secrets — see `guardrails/secrets.py` and `mcp/repository.py`'s `_is_secret_path`) and symlinks that could point outside the copy (a real security boundary for a workspace an untrusted-ish external project supplies).

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_api_workspace.py
import os

import pytest

from engineering_team.workspace.isolation import create_api_workspace


def test_copies_project_excluding_git_env_and_caches(tmp_path):
    source = tmp_path / "project"
    (source / ".git").mkdir(parents=True)
    (source / ".git" / "HEAD").write_text("ref: refs/heads/main")
    (source / ".venv").mkdir()
    (source / ".venv" / "pyvenv.cfg").write_text("home = /usr")
    (source / "__pycache__").mkdir()
    (source / "__pycache__" / "x.pyc").write_bytes(b"\x00")
    (source / ".env").write_text("SECRET=1")
    (source / "app").mkdir()
    (source / "app" / "main.py").write_text("print('hi')\n")

    fingerprint = create_api_workspace("run-1", source, tmp_path / "runs")

    copied = {p.relative_to(fingerprint.workspace_path).as_posix() for p in fingerprint.workspace_path.rglob("*") if p.is_file()}
    assert copied == {"app/main.py"}
    assert not (fingerprint.workspace_path / ".git").exists()
    assert not (fingerprint.workspace_path / ".env").exists()


def test_rejects_symlinks_that_escape_the_source(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    (source / "app").mkdir()
    (source / "app" / "main.py").write_text("print('hi')\n")
    outside = tmp_path / "outside.py"
    outside.write_text("import os\n")
    os.symlink(outside, source / "app" / "linked.py")

    fingerprint = create_api_workspace("run-2", source, tmp_path / "runs")

    assert not (fingerprint.workspace_path / "app" / "linked.py").exists()


def test_records_a_sha256_hash_per_copied_file(tmp_path):
    import hashlib

    source = tmp_path / "project"
    source.mkdir()
    (source / "main.py").write_bytes(b"print(1)\n")
    expected = hashlib.sha256(b"print(1)\n").hexdigest()

    fingerprint = create_api_workspace("run-3", source, tmp_path / "runs")

    assert fingerprint.file_hashes["main.py"] == expected
    assert fingerprint.source_path == source.resolve()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/unit/test_api_workspace.py -v`
Expected: FAIL with `ImportError: cannot import name 'create_api_workspace'`

- [ ] **Step 3: Write the implementation**

Append to `src/engineering_team/workspace/isolation.py` (keep the existing `import re`, `import shutil`, `from pathlib import Path`, and `from .paths import resolve_inside` at the top; add the three imports below alongside them):

```python
import hashlib
from dataclasses import dataclass, field


@dataclass
class WorkspaceFingerprint:
    workspace_path: Path
    source_path: Path
    file_hashes: dict[str, str] = field(default_factory=dict)


_EXCLUDED_DIR_NAMES = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache"}


def _is_excluded(relative_parts: tuple[str, ...], name: str) -> bool:
    if name in _EXCLUDED_DIR_NAMES:
        return True
    return name == ".env" or name.startswith(".env.")


def create_api_workspace(
    run_id: str, source: str | Path, workspace_root: str | Path
) -> WorkspaceFingerprint:
    """Copy `source` into an isolated, hash-fingerprinted workspace for the API executor.

    Excludes .git/.venv/__pycache__/node_modules/caches, .env*, and any
    symlink (whether or not it escapes `source`) — a future FastAPI layer
    runs the graph against the returned workspace_path, never `source`.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
        raise ValueError("invalid run_id")
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise ValueError("source project does not exist")
    root = Path(workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = resolve_inside(root, run_id)
    if destination.exists():
        raise FileExistsError(f"run workspace already exists: {run_id}")

    file_hashes: dict[str, str] = {}
    for current_dir, dir_names, file_names in os.walk(source_path, followlinks=False):
        current = Path(current_dir)
        relative_dir = current.relative_to(source_path)
        dir_names[:] = [name for name in dir_names if not _is_excluded(relative_dir.parts, name)]
        target_dir = destination / relative_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in file_names:
            source_file = current / name
            if source_file.is_symlink() or _is_excluded(relative_dir.parts, name):
                continue
            relative_file = (relative_dir / name).as_posix()
            data = source_file.read_bytes()
            (destination / relative_dir / name).write_bytes(data)
            file_hashes[relative_file] = hashlib.sha256(data).hexdigest()

    return WorkspaceFingerprint(
        workspace_path=destination, source_path=source_path, file_hashes=file_hashes,
    )
```

Add `import os` alongside the existing `import re` / `import shutil` at the top of the file too (it is not there yet).

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/unit/test_api_workspace.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full suite and lint once more**

Run: `.venv/bin/python -m pytest -q --deselect tests/e2e/test_multimodel_evidence.py::test_one_normal_run_invokes_both_local_models_through_router`
Run: `.venv/bin/python -m ruff check src/ tests/`
Expected: both clean.

- [ ] **Step 6: Commit**

```bash
git add src/engineering_team/workspace/isolation.py tests/unit/test_api_workspace.py
git commit -m "feat: add create_api_workspace with .env/symlink exclusion and file hashes"
```

---

## Out of scope for this phase (tracked in the spec, phases 2-4)

- Persisting events to SQLite, the outbox pattern, and Kafka publishing.
- `payload_ref` actually pointing anywhere (today it is always `None`; `payload` carries the data inline).
- FastAPI endpoints, SSE delivery, `Last-Event-ID` replay.
- The frontend port and `EventSource` client.
- Apply staging, tokens, and Docker Compose/Kafka.
