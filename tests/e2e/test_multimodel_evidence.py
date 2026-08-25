import json
import os
from pathlib import Path

from engineering_team.config import Settings
from engineering_team.observability.evaluation import run_multimodel_acceptance


def test_one_normal_run_invokes_both_local_models_through_router(tmp_path) -> None:
    settings = Settings(
        _env_file=None,
        workspace_root=str(tmp_path / "runs"),
        rag_persist_directory=str(tmp_path / "chroma"),
        cloud_enabled=False,
    )

    report = Path("evaluation/reports/multimodel-live.json")
    if os.getenv("RUN_LIVE_MULTIMODEL") == "1" or not report.exists():
        evidence = run_multimodel_acceptance(
            settings,
            requirement="Provide a password-recovery link that expires after 15 minutes and can be used only once.",
            report_path=report,
        )
    else:
        evidence = json.loads(report.read_text(encoding="utf-8"))

    assert evidence["final_status"] == "APPROVED"
    assert evidence["route_history"] == [
        "Product", "Architecture", "Developer", "Security", "Testing", "Reviewer", "FinalReport"
    ]
    assert [(item["agent"], item["actual_model"]) for item in evidence["model_usage"]] == [
        ("Product", "qwen3.5:9b"),
        ("Architecture", "qwen3.5:4b"),
        ("Developer", "qwen3.5:9b"),
        ("Security", "qwen3.5:9b"),
        ("Testing", "qwen3.5:4b"),
        ("Reviewer", "qwen3.5:9b"),
    ]
    assert all(item["provider"] == "ollama" for item in evidence["model_usage"])
    assert all(item["structured_output_success"] for item in evidence["model_usage"])
    assert all(not item["fallback_used"] and item["error"] is None for item in evidence["model_usage"])
    assert evidence["bonus_pass"] is True
    assert evidence["trace_id"]
