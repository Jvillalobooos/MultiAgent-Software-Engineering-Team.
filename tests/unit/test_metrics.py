from engineering_team.observability.metrics import aggregate


def test_aggregate_never_invents_unavailable_metrics() -> None:
    report = aggregate([{"observed_status": "APPROVED", "iterations": 1, "errors": []}])
    assert report["average_duration"] == "unavailable"
    assert report["approved"] == 1


def test_aggregate_reports_required_real_counts_and_model_latency() -> None:
    records = [
        {
            "observed_status": "REJECTED", "duration": 2.0, "iterations": 1,
            "llm_calls": 6, "tool_calls": 2, "retrievals": 3,
            "errors": ["RAG_ERROR"],
            "model_usage": [
                {"agent": "Testing", "actual_model": "qwen3.5:4b", "latency_ms": 100,
                 "usage": None, "fallback_used": False, "structured_output_success": True}
            ],
        }
    ]

    report = aggregate(records)

    assert report["average_llm_calls"] == 6
    assert report["average_tool_calls"] == 2
    assert report["average_retrievals"] == 3
    assert report["average_tokens_usage"] == "unavailable"
    assert report["latency_by_agent"] == {"Testing": 100.0}
    assert report["latency_by_model"] == {"qwen3.5:4b": 100.0}
    assert report["cloud_fallback_count"] == 0
    assert report["errors_by_type"] == {"RAG_ERROR": 1}
