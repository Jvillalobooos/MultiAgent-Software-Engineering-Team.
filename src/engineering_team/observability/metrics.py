from collections import Counter, defaultdict
from typing import Any


def _average(values: list[float | int]) -> float | str:
    return sum(values) / len(values) if values else "unavailable"


def _value(item: Any, key: str, default: Any = None) -> Any:
    return item.get(key, default) if isinstance(item, dict) else getattr(item, key, default)


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"runs": 0}
    numeric = lambda key: [item[key] for item in records if item.get(key) is not None]
    usages = [usage for record in records for usage in record.get("model_usage", [])]
    latency_agent: dict[str, list[float]] = defaultdict(list)
    latency_model: dict[str, list[float]] = defaultdict(list)
    token_totals: list[int] = []
    fallback_count = 0
    structured_success = 0
    structured_failure = 0
    for usage in usages:
        latency = _value(usage, "latency_ms")
        agent = _value(usage, "agent")
        model = _value(usage, "actual_model") or _value(usage, "requested_model")
        if latency is not None:
            latency_agent[str(agent)].append(latency)
            latency_model[str(model)].append(latency)
        provider_usage = _value(usage, "usage")
        if provider_usage:
            token_totals.append(
                sum(value for key, value in provider_usage.items() if "count" in key and isinstance(value, int))
            )
        fallback_count += bool(_value(usage, "fallback_used", False))
        if _value(usage, "structured_output_success", False):
            structured_success += 1
        else:
            structured_failure += 1
    return {
        "runs": len(records),
        "average_duration": _average(numeric("duration")),
        "average_llm_calls": _average(numeric("llm_calls")),
        "average_iterations": _average(numeric("iterations")),
        "average_tokens_usage": _average(token_totals),
        "average_tool_calls": _average(numeric("tool_calls")),
        "average_retrievals": _average(numeric("retrievals")),
        "approved": sum(item.get("observed_status") == "APPROVED" for item in records),
        "rejected": sum(item.get("observed_status") == "REJECTED" for item in records),
        "status_matches": sum(bool(item.get("status_match")) for item in records),
        "latency_by_agent": {key: _average(values) for key, values in latency_agent.items()},
        "latency_by_model": {key: _average(values) for key, values in latency_model.items()},
        "cloud_fallback_count": fallback_count,
        "cloud_fallback_rate": fallback_count / len(usages) if usages else 0,
        "structured_output_success": structured_success,
        "structured_output_failure": structured_failure,
        "errors_by_type": dict(
            Counter(error for item in records for error in item.get("errors", []))
        ),
    }
