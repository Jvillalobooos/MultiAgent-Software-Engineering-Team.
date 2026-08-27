"""Run the full engineering workflow directly against a real, external project.

Unlike ``observability.evaluation.run_multimodel_acceptance`` (which always
works against an isolated copy of the bundled ``sample_app``), this module
points Repository/Quality MCP at a caller-supplied project path. When the
Reviewer approves and ``authorize_writes=True``, the Developer's LLM-authored
file content is written for real via ``create_file``/``update_file`` — see
``ImplementationResult.file_contents`` and the write block in
``graph.stategraph.build_engineering_graph``.
"""

from __future__ import annotations

import itertools
import json
import time
import uuid
from pathlib import Path
from typing import Any

from engineering_team.agents.developer import DeveloperAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import ErrorCode, RunEventKind
from engineering_team.contracts.models import RunEvent
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.llm.cloud import CloudModelRuntime
from engineering_team.llm.runtime import LocalModelRuntime
from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient
from engineering_team.observability.event_callbacks import RunEventCallbackHandler
from engineering_team.observability.event_trace import EventEmittingTrace
from engineering_team.observability.events import NullRunEventSink, RunEventSink
from engineering_team.observability.langfuse import LangfuseTracer
from engineering_team.rag import build_retriever


def _default_test_paths(changed_files: list[str]) -> list[str] | None:
    selected = [
        path for path in changed_files
        if path.startswith(("tests/", "test/"))
        or Path(path).name.startswith("test_")
        or Path(path).name.endswith("_test.py")
    ]
    return selected or None


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

    implementation = state.get("implementation")
    review = state.get("review")
    diff_result = next(
        (item for item in state.get("tool_results", []) if item.tool_name == "get_diff"),
        None,
    )
    writes = [
        item for item in state.get("tool_results", [])
        if item.tool_name in {"create_file", "update_file"}
    ]
    errors = state.get("errors", [])
    evidence = {
        "run_id": run_id,
        "trace_id": trace.trace_id,
        "langfuse_live": trace.live,
        "project_path": str(project_root),
        "cloud_first": cloud_first,
        "final_status": state.get("final_status"),
        "route_history": state.get("route_history", []),
        "iterations": state.get("iteration", 0),
        "duration_seconds": duration,
        "authorize_writes": authorize_writes,
        "action_mode": implementation.action_mode.value if implementation else None,
        "changed_files": implementation.changed_files if implementation else [],
        "diff_summary": implementation.diff if implementation else "",
        "proposed_file_contents": implementation.file_contents if implementation else {},
        "files_written": [item.output_summary for item in writes if item.status.value == "SUCCESS"],
        "write_errors": [
            f"{item.tool_name}({item.input_summary}): {item.error}"
            for item in writes if item.status.value != "SUCCESS"
        ],
        "applied_diff": diff_result.output_summary if diff_result else "",
        "review": review.model_dump(mode="json") if review else None,
        "model_usage": [item.model_dump(mode="json") for item in state.get("model_usage", [])],
        "errors": [
            f"{item.code.value}: {item.detail}" for item in errors
        ],
        "human_review_required": bool(state.get("human_review_required")),
        "destructive_authorization_blocked": any(
            item.code is ErrorCode.TOOL_ERROR and "destructive operation" in item.detail
            for item in errors
        ),
    }
    if report_path is not None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    return evidence
