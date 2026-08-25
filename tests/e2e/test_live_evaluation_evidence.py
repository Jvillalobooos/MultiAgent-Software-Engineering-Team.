import json
from pathlib import Path


def test_five_scenario_live_evidence_uses_real_local_models_and_fixed_outcomes() -> None:
    scenarios_path = Path("evaluation/reports/scenarios-live.json")
    aggregate_path = Path("evaluation/reports/aggregate-live.json")

    assert scenarios_path.exists(), "run: python scripts/run_evaluation.py --live-models"
    assert aggregate_path.exists(), "run: python scripts/run_evaluation.py --live-models"
    records = json.loads(scenarios_path.read_text(encoding="utf-8"))
    metrics = json.loads(aggregate_path.read_text(encoding="utf-8"))

    assert [item["id"] for item in records] == ["SC-01", "SC-02", "SC-03", "SC-04", "SC-05"]
    assert [item["expected_status"] for item in records] == [
        "APPROVED", "APPROVED", "APPROVED", "REJECTED", "REJECTED"
    ]
    assert [item["observed_status"] for item in records] == [
        "APPROVED", "APPROVED", "APPROVED", "REJECTED", "REJECTED"
    ]
    assert all(item["status_match"] and item["pass"] for item in records)
    assert all(item["langfuse_live"] and item["trace_id"] for item in records)
    assert all(any(ref.startswith("mcp://") for ref in item["tool_evidence"]) for item in records)
    assert all(item["llm_calls"] > 0 and item["model_usage"] for item in records)
    usage = [entry for item in records for entry in item["model_usage"]]
    assert {item["actual_model"] for item in usage} == {"qwen3.5:4b", "qwen3.5:9b"}
    assert all(item["provider"] == "ollama" and not item["fallback_used"] for item in usage)
    assert metrics["average_llm_calls"] > 0
    assert metrics["approved"] == 3
    assert metrics["rejected"] == 2
    assert metrics["latency_by_agent"]
    assert set(metrics["latency_by_model"]) == {"qwen3.5:4b", "qwen3.5:9b"}
