"""Project the real workflow evidence onto the immutable frontend contract."""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from engineering_team.guardrails.secrets import redact_secrets

_AGENTS = {
    "product": "product", "architecture": "architecture", "developer": "developer",
    "security": "security", "testing": "testing", "reviewer": "reviewer",
    "human_review": "human_review", "human_review_required": "human_review",
    "security_hitl": "human_review",
}
_SENSITIVE_KEYS = {
    "api_key", "apikey", "secret", "secret_key", "password", "access_token",
    "authorization", "gemini_api_key", "groq_api_key", "langfuse_secret_key",
}


class EventForwardingTrace:
    """Fan out runtime instrumentation without reading state back from Langfuse."""

    def __init__(self, delegate: Any, observer: Any) -> None:
        self._delegate = delegate
        self._observer = observer

    @property
    def trace_id(self) -> str:
        return self._delegate.trace_id

    @property
    def live(self) -> bool:
        return self._delegate.live

    def record(self, name: str, **kwargs: Any) -> str:
        self._observer({
            "name": name,
            "type": kwargs.get("as_type", "span"),
            "input": kwargs.get("input"),
            "output": kwargs.get("output"),
            "metadata": kwargs.get("metadata") or {},
            "level": kwargs.get("level"),
            "status_message": kwargs.get("status_message"),
            "model": kwargs.get("model"),
            "usage_details": kwargs.get("usage_details"),
        })
        return self._delegate.record(name, **kwargs)

    def finish(self, final_report: Any) -> None:
        self._delegate.finish(final_report)


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _safe_transport(value: Any) -> Any:
    value = _plain(value)
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _safe_transport(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_transport(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value


def _agent(value: Any, default: str = "human_review") -> str:
    value = getattr(value, "value", value)
    return _AGENTS.get(str(value or "").lower(), default)


def _json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return redact_secrets(value)
    return json.dumps(_safe_transport(value), ensure_ascii=False, separators=(",", ":"), default=str)


def _metadata(value: Any) -> dict[str, str | int | float]:
    output: dict[str, str | int | float] = {}
    for key, item in dict(value or {}).items():
        item = getattr(item, "value", item)
        if isinstance(item, bool):
            output[str(key)] = str(item).lower()
        elif isinstance(item, (str, int, float)) and not isinstance(item, bool):
            output[str(key)] = redact_secrets(item) if isinstance(item, str) else item
    return output


def run_event_from_trace(
    *, run_id: str, sequence: int, trace_event: Mapping[str, Any], observed_at: int | None = None,
) -> dict[str, Any]:
    """Convert one real trace observation without making it a state source."""
    metadata = _metadata(trace_event.get("metadata"))
    output_value = _plain(trace_event.get("output"))
    if isinstance(output_value, dict):
        if "allowed_role" in output_value and "agent" not in metadata:
            metadata["agent"] = str(output_value["allowed_role"])
        for source_key, target_key in (
            ("status", "status"), ("duration_ms", "duration_ms"),
            ("tool_name", "tool"),
        ):
            value = getattr(output_value.get(source_key), "value", output_value.get(source_key))
            if isinstance(value, (str, int, float)):
                metadata[target_key] = value
    elif isinstance(output_value, list) and output_value and isinstance(output_value[0], dict):
        evidence = output_value[0]
        for source_key, target_key in (
            ("source", "source"), ("section", "section"), ("score", "relevance"),
        ):
            value = evidence.get(source_key)
            if isinstance(value, (str, int, float)):
                metadata[target_key] = value
    raw_level = str(trace_event.get("level") or "info").lower()
    level = "error" if raw_level == "error" else "warn" if raw_level in {"warn", "warning"} else "info"
    raw_type = str(trace_event.get("type") or "span").lower()
    if level == "error":
        event_type = "error"
    elif raw_type in {"retriever", "rag"}:
        event_type = "rag"
    elif raw_type in {"tool", "mcp"}:
        event_type = "tool"
    else:
        event_type = "model"
    name = str(trace_event.get("name") or "workflow event")
    agent_value = metadata.get("agent") or metadata.get("from") or (
        name if name.lower() in _AGENTS else None
    )
    event: dict[str, Any] = {
        "id": f"{run_id}-{sequence}",
        "name": name,
        "type": event_type,
        "level": level,
        "status_message": redact_secrets(str(trace_event.get("status_message") or name)),
        "metadata": metadata,
        "agent": _agent(agent_value),
        "iteration": int(metadata.get("iteration", 0)),
        "at": observed_at if observed_at is not None else int(time.time() * 1000),
    }
    for field in ("model",):
        if trace_event.get(field) is not None:
            event[field] = str(trace_event[field])
    for field in ("input", "output"):
        rendered = _json_text(trace_event.get(field))
        if rendered is not None:
            event[field] = rendered
    usage = trace_event.get("usage_details")
    if usage:
        event["usage_details"] = {
            "input_tokens": int(usage.get("input_tokens", usage.get("prompt_tokens", 0))),
            "output_tokens": int(usage.get("output_tokens", usage.get("completion_tokens", 0))),
            "latency_ms": int(usage.get("latency_ms", metadata.get("latency_ms", 0))),
        }
    return event


def _diff_files(
    implementation: Mapping[str, Any] | None, diff_text: str | None, actual_paths: list[str],
) -> list[dict[str, Any]]:
    # `diff_text` (the get_diff MCP tool's difflib output over real before/after file
    # content) is authoritative; implementation.diff is free-text the model wrote about
    # its own change and is often empty or malformed even on a real successful write.
    # None means no verified diff was collected; an empty verified diff means no
    # textual change, even if a model claims otherwise or a file was rewritten.
    if diff_text == "":
        return []
    diff = diff_text if diff_text is not None else str((implementation or {}).get("diff") or "")
    paths = actual_paths or list((implementation or {}).get("changed_files") or [])
    if not diff and not paths:
        return []
    sections: dict[str, list[str]] = defaultdict(list)
    current = paths[0] if len(paths) == 1 else None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            candidate = line[4:].removeprefix("b/")
            if candidate != "/dev/null":
                current = candidate
        if current:
            sections[current].append(line)
    if diff_text is None:
        for path in paths:
            sections.setdefault(path, [])

    files: list[dict[str, Any]] = []
    for path, raw_lines in sections.items():
        old_no = new_no = 0
        lines: list[dict[str, Any]] = []
        additions = deletions = 0
        for raw in raw_lines:
            if raw.startswith(("--- ", "+++ ")):
                continue
            if raw.startswith("@@"):
                match = re.search(r"-(\d+)(?:,\d+)? \+(\d+)", raw)
                if match:
                    old_no, new_no = map(int, match.groups())
                lines.append({"type": "meta", "text": raw})
            elif raw.startswith("+"):
                additions += 1
                lines.append({"type": "add", "text": raw[1:], "newNo": new_no})
                new_no += 1
            elif raw.startswith("-"):
                deletions += 1
                lines.append({"type": "del", "text": raw[1:], "oldNo": old_no})
                old_no += 1
            else:
                text = raw.removeprefix(" ")
                lines.append({"type": "ctx", "text": text, "oldNo": old_no, "newNo": new_no})
                old_no += 1
                new_no += 1
        files.append({
            "path": path,
            "language": "python" if path.endswith(".py") else "markdown",
            "additions": additions, "deletions": deletions, "lines": lines,
        })
    return files


def _route_steps(state: Mapping[str, Any], completed_at: str) -> list[dict[str, Any]]:
    history = [str(item) for item in state.get("route_history", [])]
    review = _plain(state.get("review")) or {}
    steps: list[dict[str, Any]] = []
    iteration = 1
    for index, item in enumerate(history):
        if item != "Reviewer":
            continue
        next_item = history[index + 1] if index + 1 < len(history) else "FinalReport"
        if next_item == "FinalReport":
            target, decision = "reviewer", "APPROVED"
        elif next_item in {"HUMAN_REVIEW_REQUIRED", "security_hitl"}:
            target, decision = "human_review", "ESCALATED"
        else:
            target, decision = _agent(next_item), "REJECTED"
        steps.append({
            "iteration": iteration, "from": "reviewer", "to": target,
            "decision": decision, "reason": str(review.get("reason") or next_item),
            "score": float(review.get("score") or 0), "at": completed_at,
        })
        iteration += 1
    if not steps and state.get("final_status") == "HUMAN_REVIEW_REQUIRED":
        steps.append({
            "iteration": max(1, int(state.get("iteration", 0)) + 1),
            "from": "human_review", "to": "human_review", "decision": "ESCALATED",
            "reason": "Workflow requires human review.", "score": float(review.get("score") or 0),
            "at": completed_at,
        })
    return steps


def final_report_from_state(state_value: Any, *, completed_at: str | None = None) -> dict[str, Any]:
    state = _plain(state_value)
    completed_at = completed_at or datetime.now().astimezone().isoformat(timespec="seconds")
    review = _plain(state.get("review")) or {}
    final_status = str(state.get("final_status") or "HUMAN_REVIEW_REQUIRED")
    public_status = final_status if final_status in {"APPROVED", "REJECTED", "HUMAN_REVIEW_REQUIRED"} else "HUMAN_REVIEW_REQUIRED"
    subscore_keys = ("requirements", "architecture", "security", "testing", "implementation", "rag_grounding")
    raw_subscores = review.get("subscores") or {}

    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for raw in state.get("model_usage", []):
        item = _plain(raw)
        agent = _agent(item.get("agent"))
        provider = "local" if str(item.get("provider", "")).lower() in {"ollama", "local"} else "cloud"
        model = str(item.get("actual_model") or item.get("requested_model") or "unavailable")
        grouped[(agent, model, provider)].append(item)
    failed_agents = {
        _agent(_plain(raw).get("agent"))
        for raw in state.get("model_usage", [])
        if _plain(raw).get("error")
    }
    model_usage = []
    for (agent, model, provider), items in grouped.items():
        inputs = outputs = latency = 0
        last_failure: Mapping[str, Any] | None = None
        for item in items:
            usage = item.get("usage") or {}
            inputs += int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
            outputs += int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
            latency += int(item.get("latency_ms", 0) or 0)
            if item.get("error"):
                last_failure = item
        entry: dict[str, Any] = {
            "agent": agent, "model": model, "provider": provider, "calls": len(items),
            "input_tokens": inputs, "output_tokens": outputs,
            "avg_latency_ms": round(latency / len(items)),
        }
        if last_failure is not None:
            if last_failure.get("http_status") is not None:
                entry["http_status"] = int(last_failure["http_status"])
            if last_failure.get("error_category"):
                entry["error_category"] = str(last_failure["error_category"])
            if last_failure.get("retryable") is not None:
                entry["retryable"] = bool(last_failure["retryable"])
        elif agent in failed_agents:
            entry["fallback_succeeded"] = True
        model_usage.append(entry)

    errors = []
    for raw in state.get("errors", []):
        item = _plain(raw)
        errors.append({
            "code": str(getattr(item.get("code"), "value", item.get("code", "WORKFLOW_ERROR"))),
            "message": redact_secrets(str(item.get("detail") or item.get("message") or "Workflow error")),
            "agent": _agent(item.get("source_stage")),
            "iteration": int(state.get("iteration", 0)),
        })
    evidence = []
    for raw in state.get("rag_evidence", []):
        item = _plain(raw)
        evidence.append({
            "source": str(item.get("source", "")), "section": str(item.get("section", "")),
            "score": float(item.get("score") or 0), "agent": _agent(item.get("domain"), "architecture"),
            "snippet": str(item.get("fragment", "")),
        })
    tools = []
    workspace_changed = False
    written_paths: list[str] = []
    diff_tool_text = None
    for raw in state.get("tool_results", []):
        item = _plain(raw)
        raw_status = str(getattr(item.get("status"), "value", item.get("status", "FAIL")))
        if item.get("tool_name") in {"create_file", "update_file"} and raw_status == "SUCCESS":
            workspace_changed = True
            written_path = str(item.get("output_summary") or "").strip()
            if written_path and written_path not in written_paths:
                written_paths.append(written_path)
        if item.get("tool_name") == "get_diff" and raw_status == "SUCCESS":
            diff_tool_text = str(item.get("output_summary") or "")
        tools.append({
            "name": str(item.get("tool_name", "")),
            "status": raw_status if raw_status in {"SUCCESS", "FAIL", "DENIED"} else "FAIL",
            "duration_ms": int(item.get("duration_ms", 0)), "agent": _agent(item.get("allowed_role")),
            "detail": redact_secrets(str(item.get("error") or item.get("output_summary") or raw_status)),
        })
    implementation = _plain(state.get("implementation"))
    return {
        "route_history": _route_steps(state, completed_at),
        "model_usage": model_usage,
        "changed_files": _diff_files(implementation, diff_tool_text, written_paths),
        # Whether files were actually written into the run's sandboxed workspace copy,
        # derived from real create_file/update_file tool successes -- not the model's
        # self-reported action_mode, which can mismatch what tool calls actually did.
        "applied_diff": workspace_changed,
        "workspace_changed": workspace_changed,
        "actual_changed_paths": written_paths,
        "source_applied": False,
        "review": {
            "status": public_status, "score": float(review.get("score") or 0),
            "subscores": {key: float(raw_subscores.get(key, 0)) for key in subscore_keys},
            "problems": [str(item) for item in review.get("problems", [])],
            "reason": str(review.get("reason") or (errors[-1]["message"] if errors else final_status)),
        },
        "errors": errors, "rag_evidence": evidence, "tool_results": tools,
    }


def failure_state(run_id: str, message: str) -> dict[str, Any]:
    return {
        "run_id": run_id, "iteration": 0, "final_status": "HUMAN_REVIEW_REQUIRED",
        "route_history": ["HUMAN_REVIEW_REQUIRED"], "implementation": None, "review": None,
        "model_usage": [], "rag_evidence": [], "tool_results": [],
        "errors": [{"code": "WORKFLOW_ERROR", "source_stage": "human_review", "detail": redact_secrets(message)}],
    }
