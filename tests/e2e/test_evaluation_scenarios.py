from pathlib import Path

from engineering_team.config import Settings
from engineering_team.mcp.quality import QualityMCP
from engineering_team.observability.evaluation import SCENARIOS, EvaluationHarness
from engineering_team.rag import build_retriever


def test_exactly_five_scenarios_execute_with_fixed_expected_outcomes(tmp_path) -> None:
    settings = Settings(_env_file=None)
    retriever = build_retriever(settings, tmp_path / "chroma", reindex=True)
    harness = EvaluationHarness(
        retriever=retriever,
        quality_mcp=QualityMCP(Path.cwd()),
        test_paths=["tests/integration/test_sample_app.py"],
        workspace_root=tmp_path / "runs",
    )

    records = harness.run_all()
    harness.write(records, "evaluation/reports/scenarios.json")

    assert len(SCENARIOS) == 5
    assert [item.expected_status for item in SCENARIOS] == [
        "APPROVED", "APPROVED", "APPROVED", "REJECTED", "REJECTED"
    ]
    assert [item.observed_status for item in records] == [
        "APPROVED", "APPROVED", "APPROVED", "REJECTED", "REJECTED"
    ]
    assert all(item.status_match and item.pass_ for item in records)
    assert all(item.acceptance_evidence for item in records)
    assert all("scenario_acceptance" in item.tools_used for item in records)
    assert "15 minutes" in " ".join(records[0].observed_findings)
    assert "single-use" in " ".join(records[0].observed_findings)
    assert "5 failed attempts" in " ".join(records[1].observed_findings)
    assert "authorized user" in " ".join(records[2].observed_findings)
    assert "Maximum 5" in " ".join(records[2].observed_findings)
    assert "expire" in " ".join(records[3].observed_findings)
    assert "IDOR" in " ".join(records[4].observed_findings)
    assert all(item.tools_used for item in records)
    assert all(item.trace_id for item in records)
    assert all(len(item.scores) == 6 for item in records)
