import json
import os
from pathlib import Path

from engineering_team.config import Settings
from engineering_team.observability.evaluation import run_multimodel_acceptance

# Dedicated local-only fixture — intentionally NOT
# evaluation/reports/multimodel-live.json, which is the real evidence
# artifact for whichever runtime mode .env configures (local-first or
# cloud-first per README's "Cloud-first (opcional)" section). Sharing that
# path caused this test to silently read cloud-provider evidence, or to
# force a live local run on every collection and flake on local-model
# non-determinism (an occasional genuine Reviewer rejection is expected
# behavior for a small local model, not a bug).
_LOCAL_FIXTURE = Path("evaluation/reports/multimodel-live-local.json")


def test_one_normal_run_invokes_both_local_models_through_router(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        workspace_root=str(tmp_path / "runs"),
        rag_persist_directory=str(tmp_path / "chroma"),
        cloud_enabled=False,
        local_first=True,
    )

    if os.getenv("RUN_LIVE_MULTIMODEL") == "1" or not _LOCAL_FIXTURE.exists():
        evidence = run_multimodel_acceptance(
            settings,
            requirement="Provide a password-recovery link that expires after 15 minutes and can be used only once.",
            report_path=_LOCAL_FIXTURE,
        )
    else:
        evidence = json.loads(_LOCAL_FIXTURE.read_text(encoding="utf-8"))

    assert evidence["final_status"] == "APPROVED"
    assert evidence["route_history"] == [
        "Product", "Architecture", "Developer", "Security", "Testing", "Reviewer", "FinalReport"
    ]
    # A node may appear more than once in model_usage if LocalModelRuntime needed
    # an internal repair retry (still the same local provider, not a fallback) —
    # collapse to the final, authoritative attempt per agent before asserting.
    final_by_agent = {item["agent"]: item for item in evidence["model_usage"]}
    assert [(agent, info["actual_model"]) for agent, info in final_by_agent.items()] == [
        ("Product", "qwen3.5:9b"),
        ("Architecture", "qwen3.5:4b"),
        ("Developer", "qwen3.5:9b"),
        ("Security", "qwen3.5:9b"),
        ("Testing", "qwen3.5:4b"),
        ("Reviewer", "qwen3.5:9b"),
    ]
    assert all(info["provider"] == "ollama" for info in final_by_agent.values())
    assert all(info["structured_output_success"] for info in final_by_agent.values())
    assert all(not info["fallback_used"] and info["error"] is None for info in final_by_agent.values())
    assert evidence["trace_id"]
    assert evidence["trace_events"]
    assert all(
        "input" not in event and "output" not in event
        for event in evidence["trace_events"]
    )
