"""The single governed LangGraph orchestrator for the engineering workflow."""

from __future__ import annotations

import hashlib
from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from engineering_team.agents.architecture import ArchitectureAgent
from engineering_team.agents.developer import DeveloperAgent
from engineering_team.agents.product import ProductAgent
from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.agents.testing import TestingAgent
from engineering_team.contracts.enums import (
    ActionMode,
    AgentRole,
    ErrorCode,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    ToolStatus,
)
from engineering_team.contracts.models import FinalReport, ReviewerDecision, WorkflowError
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context

from .routers import review_route, security_route


class WalkingState(TypedDict):
    visited: list[str]
    final_status: str


class WorkflowState(TypedDict, total=False):
    run_id: str
    requirement: str
    specification: object
    repository_context: dict
    architecture: object
    implementation: object
    security_review: object
    test_results: list
    review: object
    rag_evidence: list
    tool_results: list
    model_usage: list
    iteration: int
    errors: list
    human_review_required: bool
    final_status: str
    remediation_request: str
    next_validation_path: str
    cloud_escalations_by_agent: dict
    cloud_escalations_run: int
    local_retries_by_stage: dict
    local_repairs_by_stage: dict
    trace_id: str
    route_history: list
    final_report: object
    human_decision: str


def approval_problems(state: EngineeringState) -> list[str]:
    """Return deterministic material-evidence gaps for an implementable run."""
    if not state.repository_context.get("implementation_required", False):
        return []
    implementation = state.implementation
    if implementation is None:
        return ["implementation is missing"]
    problems: list[str] = []
    if implementation.action_mode.value != "APPLIED":
        problems.append("implementation is not applied")
    if not implementation.changed_files:
        problems.append("implementation changed_files is empty")
    writes = [
        item for item in state.tool_results
        if item.tool_name in {"create_file", "update_file"} and item.status is ToolStatus.SUCCESS
    ]
    if not writes:
        problems.append("successful Repository MCP write evidence is missing")
    diffs = [
        item for item in state.tool_results
        if item.tool_name == "get_diff" and item.status is ToolStatus.SUCCESS
    ]
    if not diffs or not implementation.diff.strip():
        problems.append("successful non-empty Repository MCP diff is missing")
    latest_test = state.test_results[-1] if state.test_results else None
    if latest_test is None or latest_test.status is not ToolStatus.SUCCESS:
        problems.append("successful workspace test validation is missing")
    elif not latest_test.generated_tests:
        problems.append("requirement-specific generated tests are missing")
    if state.security_review is not None and state.security_review.status.value == "FAIL":
        problems.append("security review failed")
    if any(error.code in {ErrorCode.MCP_ERROR, ErrorCode.RAG_ERROR} for error in state.errors):
        problems.append("required MCP or RAG evidence is unavailable")
    return problems


def implementation_pre_gate_problems(state: EngineeringState) -> list[str]:
    """Return evidence gaps that make downstream validation futile."""
    if not state.repository_context.get("implementation_required", False):
        return []
    implementation = state.implementation
    if implementation is None:
        return ["implementation is missing"]
    problems: list[str] = []
    if implementation.action_mode is not ActionMode.APPLIED:
        problems.append("implementation is not applied")
    if not implementation.changed_files:
        problems.append("implementation changed_files is empty")
    if not any(
        item.tool_name in {"create_file", "update_file"} and item.status is ToolStatus.SUCCESS
        for item in state.tool_results
    ):
        problems.append("successful Repository MCP write evidence is missing")
    if not any(
        item.tool_name == "get_diff" and item.status is ToolStatus.SUCCESS
        for item in state.tool_results
    ) or not implementation.diff.strip():
        problems.append("successful non-empty Repository MCP diff is missing")
    return problems


def _visit(role: str):
    def node(state: WalkingState) -> dict[str, object]:
        return {"visited": [*state.get("visited", []), role]}
    return node


def _review(state: WalkingState) -> dict[str, object]:
    return {"visited": [*state.get("visited", []), "Reviewer"], "final_status": "APPROVED"}


def build_walking_graph():
    graph = StateGraph(WalkingState)
    graph.add_node("Product", _visit("Product"))
    graph.add_node("Architecture", _visit("Architecture"))
    graph.add_node("Developer", _visit("Developer"))
    graph.add_node("Security", _visit("Security"))
    graph.add_node("Testing", _visit("Testing"))
    graph.add_node("Reviewer", _review)
    graph.add_edge(START, "Product")
    graph.add_edge("Product", "Architecture")
    graph.add_edge("Architecture", "Developer")
    graph.add_edge("Developer", "Security")
    graph.add_edge("Security", "Testing")
    graph.add_edge("Testing", "Reviewer")
    graph.add_edge("Reviewer", END)
    return graph.compile()


def _report(state: EngineeringState, status: str) -> FinalReport:
    return FinalReport(
        feature="Autonomous Software Engineering Team",
        status=status,
        requirements=state.specification.objective if state.specification else state.requirement,
        architecture=state.architecture.impact if state.architecture else "unavailable",
        security=state.security_review.status.value if state.security_review else "unavailable",
        testing=state.test_results[-1].status.value if state.test_results else "unavailable",
        implementation=state.implementation.validation_result if state.implementation else "unavailable",
        risk=(state.security_review.highest_severity.value if state.security_review else "unknown"),
        iterations=state.iteration,
        documentation_used=list(dict.fromkeys(item.source for item in state.rag_evidence)),
        tools_executed=[item.tool_name for item in state.tool_results],
        models_used=[item.actual_model or item.requested_model for item in state.model_usage],
        errors_degradations=[f"{item.code.value}: {item.detail}" for item in state.errors],
        trace_id=state.trace_id or state.run_id,
        next_action="none" if status == "APPROVED" else "human review",
    )


def build_engineering_graph(
    *,
    agent_overrides: dict[AgentRole, Any] | None = None,
    quality_mcp: Any | None = None,
    repository_mcp: Any | None = None,
    retriever: Any | None = None,
    model_runtime: Any | None = None,
    cloud_runtime: Any | None = None,
    trace: Any | None = None,
    test_paths: list[str] | None = None,
    interactive_hitl: bool = False,
    progress: Any | None = None,
):
    """Compile normal, remediation, MCP/RAG, and HITL routes as real nodes."""
    graph = StateGraph(WorkflowState)
    agents: dict[AgentRole, Any] = {
        AgentRole.PRODUCT: ProductAgent(), AgentRole.ARCHITECTURE: ArchitectureAgent(),
        AgentRole.DEVELOPER: DeveloperAgent(), AgentRole.SECURITY: SecurityAgent(),
        AgentRole.TESTING: TestingAgent(), AgentRole.REVIEWER: ReviewerAgent(),
    }
    agents.update(agent_overrides or {})
    targets = {
        AgentRole.PRODUCT: "specification", AgentRole.ARCHITECTURE: "architecture",
        AgentRole.DEVELOPER: "implementation", AgentRole.SECURITY: "security_review",
        AgentRole.TESTING: "test_results", AgentRole.REVIEWER: "review",
    }

    def mcp_trace_metadata(adapter: Any) -> dict[str, Any]:
        return {
            "transport": getattr(adapter, "transport", "direct-backend"),
            "protocol_version": getattr(adapter, "last_protocol_version", None),
            "server": getattr(adapter, "last_server_name", type(adapter).__name__),
        }

    def preserve_tool_result(
        result: Any,
        role: AgentRole,
        errors: list[WorkflowError],
        tool_results: list[Any],
        adapter: Any,
    ) -> bool:
        """Preserve one MCP result and return whether required MCP evidence is unavailable."""
        tool_results.append(result)
        if trace is not None:
            trace.record(
                "MCP call", as_type="tool", output=result.model_dump(mode="json"),
                metadata=mcp_trace_metadata(adapter),
            )
        if result.status not in {ToolStatus.UNAVAILABLE, ToolStatus.FAIL}:
            return False
        code = (
            ErrorCode.MCP_ERROR
            if result.status is ToolStatus.UNAVAILABLE
            else ErrorCode.TOOL_ERROR
        )
        error = WorkflowError(
            code=code,
            source_stage=role.value,
            retryable=False,
            detail=f"{result.tool_name}: {result.error or result.status.value}",
            evidence_reference=result.evidence_reference,
        )
        errors.append(error)
        if trace is not None:
            trace.record(
                code.value,
                level="ERROR",
                status_message=error.detail,
                output=result.model_dump(mode="json"),
                metadata={"agent": role.value, "tool": result.tool_name},
            )
        return result.status is ToolStatus.UNAVAILABLE

    def apply_mutations(candidate: Any, role: AgentRole, adapter: Any, tool_results: list[Any], errors: list[WorkflowError]) -> Any:
        """Apply only validated MCP mutations and derive evidence from returned tools."""
        mutations = getattr(candidate, "mutations", []) if role is AgentRole.DEVELOPER else getattr(candidate, "test_mutations", [])
        if adapter is None or not mutations:
            return candidate
        inspected = {
            item.input_summary.removeprefix("path=").replace("\\", "/")
            for item in tool_results
            if item.tool_name in {"read_file", "get_file_content"}
            and item.status is ToolStatus.SUCCESS and item.input_summary.startswith("path=")
        }
        writes: list[Any] = []
        for mutation in mutations:
            if role is AgentRole.DEVELOPER and mutation.path not in inspected:
                errors.append(WorkflowError(
                    code=ErrorCode.TOOL_ERROR, source_stage=role.value, retryable=False,
                    detail=f"uninspected mutation path: {mutation.path}",
                ))
                continue
            operation = adapter.create_file if mutation.operation == "create" else adapter.update_file
            result = operation(role, mutation.path, mutation.content)
            preserve_tool_result(result, role, errors, tool_results, adapter)
            if result.status is ToolStatus.SUCCESS:
                writes.append(result)
        if role is not AgentRole.DEVELOPER or not writes:
            return candidate
        diff = adapter.get_diff(role)
        preserve_tool_result(diff, role, errors, tool_results, adapter)
        if diff.status is ToolStatus.SUCCESS and diff.output_summary.strip():
            return candidate.model_copy(update={
                "action_mode": ActionMode.APPLIED,
                "changed_files": list(dict.fromkeys(item.output_summary for item in writes)),
                "diff": diff.output_summary,
                "evidence": list(dict.fromkeys([
                    *candidate.evidence,
                    *(item.evidence_reference or item.tool_name for item in writes),
                    diff.evidence_reference or diff.tool_name,
                ])),
                "validation_result": "APPLIED from successful Repository MCP writes and real get_diff",
            })
        return candidate

    def developer_inspection_fingerprint(tool_results: list[Any]) -> str:
        inspected = [
            f"{item.input_summary}:{item.output_summary}"
            for item in tool_results
            if item.allowed_role is AgentRole.DEVELOPER
            and item.tool_name in {"read_file", "get_file_content"}
            and item.status is ToolStatus.SUCCESS
            and item.input_summary.startswith("path=")
            and DeveloperAgent.is_implementation_candidate(item.input_summary[5:])
        ]
        return hashlib.sha256("\n".join(inspected).encode()).hexdigest()

    def make_node(role: AgentRole):
        def node(raw_state: dict[str, Any]) -> dict[str, Any]:
            current = EngineeringState.model_validate(raw_state)
            if progress is not None:
                progress(role, current.iteration)
            if role is AgentRole.REVIEWER:
                gaps = approval_problems(current)
                if gaps:
                    decision = ReviewerDecision(
                        status=ReviewerStatus.REJECTED,
                        score=45,
                        subscores={},
                        problems=gaps,
                        reason="deterministic delivery gate: " + "; ".join(gaps),
                        remediation_category=RemediationCategory.IMPLEMENTATION,
                        return_to=RouteTarget.DEVELOPER,
                        confidence=1.0,
                        evidence_references=[],
                    )
                    if trace is not None:
                        trace.record(
                            "Reviewer pre-gate", as_type="agent", output=decision.model_dump(mode="json"),
                            metadata={"iteration": current.iteration, "llm_skipped": True},
                        )
                    return {
                        "route_history": [*current.route_history, role.value],
                        "review": decision,
                        "iteration": current.iteration + 1,
                        "remediation_request": decision.reason,
                        "next_validation_path": "full",
                        "trace_id": trace.trace_id if trace is not None else current.trace_id,
                    }
            rag_evidence = list(current.rag_evidence)
            errors = list(current.errors)
            tool_results = list(current.tool_results)
            required_mcp_missing = False
            if retriever is not None and role in {
                AgentRole.ARCHITECTURE, AgentRole.SECURITY, AgentRole.TESTING
            }:
                retrieved = retriever.retrieve(current.requirement, agent=role)
                rag_evidence.extend(
                    item for item in retrieved if item.chunk_id not in {old.chunk_id for old in rag_evidence}
                )
                if retriever.last_error is not None:
                    errors.append(retriever.last_error)
                if trace is not None:
                    trace.record(
                        "RAG retrieval", as_type="retriever", input={"query": current.requirement},
                        output=[item.model_dump(mode="json") for item in retrieved],
                        metadata={"agent": role.value, "status": retriever.last_status},
                    )
            prior_developer_inspection = (
                role is AgentRole.DEVELOPER
                and any(
                    item.allowed_role is AgentRole.DEVELOPER
                    and item.tool_name in {"read_file", "get_file_content"}
                    and item.status is ToolStatus.SUCCESS
                    and item.input_summary.startswith("path=")
                    and DeveloperAgent.is_implementation_candidate(item.input_summary[5:])
                    for item in tool_results
                )
            )
            fresh_remediation_selection = (
                role is AgentRole.DEVELOPER
                and current.iteration == 1
                and bool(current.remediation_request)
            )
            if repository_mcp is not None and role in {AgentRole.ARCHITECTURE, AgentRole.DEVELOPER} and (
                not prior_developer_inspection or fresh_remediation_selection
            ):
                result = repository_mcp.list_files(role)
                required_mcp_missing |= preserve_tool_result(
                    result, role, errors, tool_results, repository_mcp
                )
                if role is AgentRole.DEVELOPER and result.status is ToolStatus.SUCCESS:
                    listed_paths = [
                        line.strip().replace("\\", "/")
                        for line in result.output_summary.splitlines()
                        if DeveloperAgent.is_implementation_candidate(line.strip().replace("\\", "/"))
                    ]
                    terms = DeveloperAgent.relevance_terms(
                        current.specification, current.architecture, current.requirement
                    )
                    if fresh_remediation_selection and current.remediation_request:
                        # Bounded remediation expansion: treat the rejection reason as a
                        # search hint only, never as authority over path safety.
                        terms = list(dict.fromkeys([
                            *terms,
                            *DeveloperAgent.relevance_terms(None, None, current.remediation_request),
                        ]))
                    search_hits: list[str] = []
                    for term in terms[:3]:
                        searched = repository_mcp.search_code(role, term)
                        required_mcp_missing |= preserve_tool_result(
                            searched, role, errors, tool_results, repository_mcp
                        )
                        if searched.status is ToolStatus.SUCCESS:
                            search_hits.extend(
                                line.strip().replace("\\", "/")
                                for line in searched.output_summary.splitlines()
                                if DeveloperAgent.is_implementation_candidate(line.strip().replace("\\", "/"))
                            )
                    already_read = {
                        item.input_summary[5:].replace("\\", "/")
                        for item in tool_results
                        if item.allowed_role is AgentRole.DEVELOPER
                        and item.tool_name in {"read_file", "get_file_content"}
                        and item.status is ToolStatus.SUCCESS
                        and item.input_summary.startswith("path=")
                    }
                    already_inspected_content = {
                        item.input_summary[5:].replace("\\", "/"): item.output_summary
                        for item in tool_results
                        if item.allowed_role is AgentRole.DEVELOPER
                        and item.tool_name in {"read_file", "get_file_content"}
                        and item.status is ToolStatus.SUCCESS
                        and item.input_summary.startswith("path=")
                    }
                    # Stage B: structural expansion. A file the Developer already
                    # inspected (this cycle or an earlier one) may reference another
                    # repository-local implementation module; that referenced module
                    # becomes a high-priority, still-unexplored candidate.
                    structural_frontier: list[str] = []
                    for source_path, content in already_inspected_content.items():
                        structural_frontier.extend(
                            DeveloperAgent.structural_references(content, source_path, listed_paths)
                        )
                    structural_frontier = [
                        path for path in dict.fromkeys(structural_frontier) if path not in already_read
                    ]
                    ranked = DeveloperAgent.rank_paths(
                        listed_paths, search_hits, terms, structural_boost=set(structural_frontier)
                    )
                    read_order = [
                        *structural_frontier,
                        *[path for path in ranked if path not in already_read and path not in structural_frontier],
                    ]
                    reads_remaining = 2
                    index = 0
                    while reads_remaining > 0 and index < len(read_order):
                        path = read_order[index]
                        index += 1
                        read = repository_mcp.read_file(role, path)
                        required_mcp_missing |= preserve_tool_result(
                            read, role, errors, tool_results, repository_mcp
                        )
                        reads_remaining -= 1
                        if read.status is ToolStatus.SUCCESS and reads_remaining > 0:
                            discovered = [
                                ref for ref in DeveloperAgent.structural_references(
                                    read.output_summary, path, listed_paths
                                )
                                if ref not in already_read and ref not in read_order[:index]
                            ]
                            if discovered:
                                read_order[index:index] = discovered
            if quality_mcp is not None and role is AgentRole.SECURITY:
                operations = [
                    getattr(quality_mcp, name) for name in (
                        "scan_dependencies", "run_security_scan"
                    ) if hasattr(quality_mcp, name)
                ]
                for operation in operations:
                    result = operation(role)
                    required_mcp_missing |= preserve_tool_result(
                        result, role, errors, tool_results, quality_mcp
                    )
            current = current.model_copy(
                update={"rag_evidence": rag_evidence, "errors": errors, "tool_results": tool_results}
            )
            if required_mcp_missing:
                return {
                    "route_history": [*current.route_history, role.value],
                    "rag_evidence": rag_evidence,
                    "errors": errors,
                    "tool_results": tool_results,
                    "model_usage": list(current.model_usage),
                    "human_review_required": True,
                    "trace_id": trace.trace_id if trace is not None else current.trace_id,
                }
            model_usage = list(current.model_usage)
            envelope = build_context(role, current, current.requirement)
            candidate = agents[role].execute(envelope)
            inspection_fingerprint = developer_inspection_fingerprint(tool_results) if role is AgentRole.DEVELOPER else ""
            no_progress_signature = hashlib.sha256(
                f"{inspection_fingerprint}\n{current.remediation_request or ''}".encode()
            ).hexdigest()
            skip_developer_model = (
                role is AgentRole.DEVELOPER
                and (
                    not candidate.changed_files
                    or (
                        current.iteration >= 2
                        and current.repository_context.get("_developer_no_progress_signature") == no_progress_signature
                        and current.implementation is not None
                        and current.implementation.action_mode is ActionMode.PROPOSED
                        and implementation_pre_gate_problems(current)
                    )
                )
            )
            if skip_developer_model:
                output = candidate
                if trace is not None:
                    trace.record(
                        "Developer no-progress", as_type="agent", output=output.model_dump(mode="json"),
                        metadata={"iteration": current.iteration, "llm_skipped": True},
                    )
            elif model_runtime is not None:
                attempt_start = len(model_runtime.attempts)
                try:
                    output, model_info = model_runtime.invoke_artifact(role, envelope, candidate)
                    attempts = model_runtime.attempts[attempt_start:]
                    model_usage.extend(attempts or [model_info])
                except RuntimeError as exc:
                    model_usage.extend(model_runtime.attempts[attempt_start:])
                    message = str(exc)
                    if message.startswith(ErrorCode.LLM_QUALITY_ERROR.value):
                        code = ErrorCode.LLM_QUALITY_ERROR
                    elif message.startswith(ErrorCode.AGENT_TIMEOUT.value):
                        code = ErrorCode.AGENT_TIMEOUT
                    else:
                        code = ErrorCode.LLM_AVAILABILITY_ERROR
                    errors.append(WorkflowError(
                        code=code, source_stage=role.value, retryable=True, detail=message,
                    ))
                    if trace is not None:
                        trace.record(
                            code.value, level="ERROR", status_message=message,
                            metadata={"agent": role.value},
                        )
                    if cloud_runtime is not None:
                        cloud_attempt_start = len(getattr(cloud_runtime, "attempts", []))
                        try:
                            output, cloud_info = cloud_runtime.invoke_artifact(
                                role,
                                envelope,
                                candidate,
                                fallback_reason=code.value,
                            )
                            model_usage.append(cloud_info)
                        except RuntimeError as cloud_exc:
                            model_usage.extend(
                                getattr(cloud_runtime, "attempts", [])[cloud_attempt_start:]
                            )
                            errors.append(WorkflowError(
                                code=ErrorCode.CLOUD_FALLBACK_UNAVAILABLE,
                                source_stage=role.value, retryable=False,
                                detail=str(cloud_exc),
                            ))
                            if trace is not None:
                                trace.record(
                                    "cloud fallback error", level="ERROR",
                                    status_message=str(cloud_exc),
                                    metadata={"agent": role.value},
                                )
                            return {
                                "route_history": [*current.route_history, role.value],
                                "errors": errors, "model_usage": model_usage,
                                "rag_evidence": rag_evidence, "tool_results": tool_results,
                                "human_review_required": True,
                                "trace_id": trace.trace_id if trace is not None else current.trace_id,
                                "cloud_escalations_by_agent": {
                                    item.value: count
                                    for item, count in cloud_runtime.budget.by_agent.items()
                                },
                                "cloud_escalations_run": cloud_runtime.budget.run_count,
                            }
                    else:
                        if trace is not None:
                            trace.record(
                                "model error", level="ERROR", status_message=message,
                                metadata={"agent": role.value, "cloud_fallback": "unavailable"},
                            )
                        return {
                            "route_history": [*current.route_history, role.value],
                            "errors": errors, "model_usage": model_usage,
                            "rag_evidence": rag_evidence, "tool_results": tool_results,
                            "human_review_required": True,
                            "trace_id": trace.trace_id if trace is not None else current.trace_id,
                        }
            else:
                output = candidate
            if role is AgentRole.DEVELOPER:
                output = apply_mutations(output, role, repository_mcp, tool_results, errors)
            if role is AgentRole.TESTING:
                output = apply_mutations(output, role, repository_mcp, tool_results, errors)
                if quality_mcp is not None:
                    result = quality_mcp.run_tests(role, output.generated_tests or test_paths)
                    required_mcp_missing |= preserve_tool_result(
                        result, role, errors, tool_results, quality_mcp
                    )
                    output = output.model_copy(update={
                        "executed_tests": [*output.executed_tests, *output.generated_tests, result.tool_name],
                        "actual_results": [*output.actual_results, result.output_summary],
                        "status": result.status,
                        "failures": ([*output.failures, result.output_summary] if result.status is not ToolStatus.SUCCESS else output.failures),
                        "evidence_references": list(dict.fromkeys([
                            *output.evidence_references, result.evidence_reference or result.tool_name,
                        ])),
                    })
                if required_mcp_missing:
                    return {
                        "route_history": [*current.route_history, role.value],
                        "rag_evidence": rag_evidence,
                        "errors": errors,
                        "tool_results": tool_results,
                        "model_usage": model_usage,
                        "human_review_required": True,
                        "trace_id": trace.trace_id if trace is not None else current.trace_id,
                    }
            if role is AgentRole.REVIEWER and output.status is ReviewerStatus.APPROVED:
                gaps = approval_problems(current)
                if gaps:
                    output = output.model_copy(update={
                        "status": ReviewerStatus.REJECTED,
                        "score": min(output.score, 45),
                        "problems": list(dict.fromkeys([*output.problems, *gaps])),
                        "reason": "deterministic delivery gate: " + "; ".join(gaps),
                        "remediation_category": RemediationCategory.IMPLEMENTATION,
                        "return_to": RouteTarget.DEVELOPER,
                        "confidence": 1.0,
                    })
            patch: dict[str, Any] = {
                "route_history": [*current.route_history, role.value],
                "rag_evidence": rag_evidence,
                "errors": errors,
                "tool_results": tool_results,
                "model_usage": model_usage,
                "trace_id": trace.trace_id if trace is not None else current.trace_id,
            }
            if role is AgentRole.DEVELOPER:
                repository_context = dict(current.repository_context)
                if output.action_mode is ActionMode.APPLIED:
                    repository_context.pop("_developer_no_progress_signature", None)
                else:
                    repository_context["_developer_no_progress_signature"] = no_progress_signature
                patch["repository_context"] = repository_context
            if cloud_runtime is not None and hasattr(cloud_runtime, "budget"):
                patch["cloud_escalations_by_agent"] = {
                    item.value: count for item, count in cloud_runtime.budget.by_agent.items()
                }
                patch["cloud_escalations_run"] = cloud_runtime.budget.run_count
            target = targets[role]
            patch[target] = [*current.test_results, output] if role is AgentRole.TESTING else output
            if role is AgentRole.REVIEWER and output.status is ReviewerStatus.REJECTED:
                patch["iteration"] = current.iteration + 1
                patch["remediation_request"] = output.reason
                patch["next_validation_path"] = (
                    "testing_only"
                    if output.remediation_category is RemediationCategory.TESTING
                    else "full"
                )
            if trace is not None:
                trace.record(
                    role.value, as_type="agent", output=output.model_dump(mode="json"),
                    metadata={"iteration": patch.get("iteration", current.iteration)},
                )
            return patch
        return node

    for role in AgentRole:
        graph.add_node(role.value, make_node(role))

    def developer_next(raw_state: dict[str, Any]) -> str:
        state = EngineeringState.model_validate(raw_state)
        if state.human_review_required:
            route = "HUMAN_REVIEW_REQUIRED"
            if trace is not None:
                trace.record("route", metadata={"from": "Developer", "to": route})
            return route
        if implementation_pre_gate_problems(state):
            route = "Reviewer"
            if trace is not None:
                trace.record("route", metadata={"from": "Developer", "to": route, "pre_gate": True})
            return route
        if (
            state.next_validation_path == "testing_only"
            and state.implementation is not None
            and not state.implementation.security_surface_changed
        ):
            route = "Testing"
        else:
            route = "Security"
        if trace is not None:
            trace.record("route", metadata={"from": "Developer", "to": route})
        return route

    def security_next(raw_state: dict[str, Any]) -> str:
        state = EngineeringState.model_validate(raw_state)
        if state.human_review_required:
            return "HUMAN_REVIEW_REQUIRED"
        route = security_route(state.security_review.highest_severity)
        if trace is not None:
            trace.record("route", metadata={"from": "Security", "to": route})
        return route

    def next_or_human(raw_state: dict[str, Any], normal: str) -> str:
        state = EngineeringState.model_validate(raw_state)
        return "HUMAN_REVIEW_REQUIRED" if state.human_review_required else normal

    def reviewer_next(raw_state: dict[str, Any]) -> str:
        state = EngineeringState.model_validate(raw_state)
        if state.human_review_required:
            return "HUMAN_REVIEW_REQUIRED"
        route = review_route(state.review, state.iteration)
        if trace is not None:
            trace.record(
                "remediation route" if route not in {"FinalReport", "HUMAN_REVIEW_REQUIRED"} else "route",
                metadata={"from": "Reviewer", "to": route, "iteration": state.iteration},
            )
        return route

    def final_node(raw_state: dict[str, Any]) -> dict[str, Any]:
        state = EngineeringState.model_validate(raw_state)
        report = _report(state, "APPROVED")
        if trace is not None:
            trace.finish(report.model_dump(mode="json"))
        return {
            "route_history": [*state.route_history, "FinalReport"],
            "final_status": "APPROVED", "final_report": report,
        }

    def human_node(raw_state: dict[str, Any], name: str = "HUMAN_REVIEW_REQUIRED") -> dict[str, Any]:
        state = EngineeringState.model_validate(raw_state)
        human_decision = state.human_decision
        if interactive_hitl:
            human_decision = str(interrupt({
                "run_id": state.run_id, "reason": name,
                "allowed_decisions": ["RESUME", "TERMINATE"],
            })).strip().upper()
            if human_decision not in {"RESUME", "TERMINATE"}:
                raise ValueError("human decision must be RESUME or TERMINATE")
            if human_decision == "RESUME":
                if trace is not None:
                    trace.record(
                        "HITL resume", metadata={"iteration": state.iteration, "reason": name}
                    )
                return {
                    "route_history": [*state.route_history, name],
                    "human_review_required": False, "final_status": None,
                    "human_decision": human_decision,
                }
        report = _report(state, "HUMAN_REVIEW_REQUIRED")
        if trace is not None:
            trace.record(name, metadata={"iteration": state.iteration, "hitl": True})
            trace.finish(report.model_dump(mode="json"))
        return {
            "route_history": [*state.route_history, name], "human_review_required": True,
            "final_status": "HUMAN_REVIEW_REQUIRED", "final_report": report,
            "human_decision": human_decision,
        }

    graph.add_node("FinalReport", final_node)
    graph.add_node("HUMAN_REVIEW_REQUIRED", human_node)
    graph.add_node("security_hitl", lambda state: human_node(state, "security_hitl"))
    graph.add_edge(START, "Product")
    graph.add_conditional_edges(
        "Product", lambda state: next_or_human(state, "Architecture"),
        {"Architecture": "Architecture", "HUMAN_REVIEW_REQUIRED": "HUMAN_REVIEW_REQUIRED"},
    )
    graph.add_conditional_edges(
        "Architecture", lambda state: next_or_human(state, "Developer"),
        {"Developer": "Developer", "HUMAN_REVIEW_REQUIRED": "HUMAN_REVIEW_REQUIRED"},
    )
    graph.add_conditional_edges(
        "Developer", developer_next,
        {"Security": "Security", "Testing": "Testing", "Reviewer": "Reviewer", "HUMAN_REVIEW_REQUIRED": "HUMAN_REVIEW_REQUIRED"},
    )
    graph.add_conditional_edges(
        "Security", security_next,
        {"Testing": "Testing", "security_hitl": "security_hitl", "HUMAN_REVIEW_REQUIRED": "HUMAN_REVIEW_REQUIRED"},
    )
    graph.add_conditional_edges(
        "Testing", lambda state: next_or_human(state, "Reviewer"),
        {"Reviewer": "Reviewer", "HUMAN_REVIEW_REQUIRED": "HUMAN_REVIEW_REQUIRED"},
    )
    graph.add_conditional_edges(
        "Reviewer", reviewer_next,
        {"FinalReport": "FinalReport", "Architecture": "Architecture", "Developer": "Developer", "HUMAN_REVIEW_REQUIRED": "HUMAN_REVIEW_REQUIRED"},
    )
    graph.add_edge("FinalReport", END)
    if interactive_hitl:
        def hitl_next(raw_state: dict[str, Any], resume_target: str) -> str:
            state = EngineeringState.model_validate(raw_state)
            return resume_target if state.human_decision == "RESUME" else "END"

        graph.add_conditional_edges(
            "HUMAN_REVIEW_REQUIRED", lambda state: hitl_next(state, "Developer"),
            {"Developer": "Developer", "END": END},
        )
        graph.add_conditional_edges(
            "security_hitl", lambda state: hitl_next(state, "Testing"),
            {"Testing": "Testing", "END": END},
        )
    else:
        graph.add_edge("HUMAN_REVIEW_REQUIRED", END)
        graph.add_edge("security_hitl", END)
    return graph.compile(checkpointer=InMemorySaver() if interactive_hitl else None)
