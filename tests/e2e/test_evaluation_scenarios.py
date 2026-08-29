from pathlib import Path

from engineering_team.config import Settings
from engineering_team.contracts.models import ModelExecutionInfo
from engineering_team.llm.router import ModelRouter
from engineering_team.mcp.quality import QualityMCP
from engineering_team.observability.evaluation import SCENARIOS, EvaluationHarness
from engineering_team.observability.metrics import aggregate
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
    harness.write(records, str(tmp_path / "scenarios.json"))

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


class RouterRecordingRuntime:
    def __init__(self, settings: Settings) -> None:
        self.router = ModelRouter(settings)
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate):
        selection = self.router.local_for(role)
        info = ModelExecutionInfo(
            agent=role,
            provider="ollama",
            requested_model=selection.model,
            actual_model=selection.model,
            model_profile=selection.model_profile,
            latency_ms=7,
            usage={"eval_count": 2},
            structured_output_success=True,
        )
        self.attempts.append(info)
        return candidate, info


class RepairRecordingRuntime(RouterRecordingRuntime):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self.repaired = False

    def invoke_artifact(self, role, envelope, candidate):
        if not self.repaired:
            selection = self.router.local_for(role)
            self.attempts.append(ModelExecutionInfo(
                agent=role, provider="ollama", requested_model=selection.model,
                actual_model=selection.model, model_profile=selection.model_profile,
                degraded=True, latency_ms=3, structured_output_success=False,
                error="LLM_QUALITY_ERROR: governed artifact contradiction",
            ))
            self.repaired = True
        return super().invoke_artifact(role, envelope, candidate)


def test_evaluation_records_model_usage_needed_by_live_aggregate(tmp_path) -> None:
    settings = Settings(_env_file=None)
    harness = EvaluationHarness(
        quality_mcp=QualityMCP(Path.cwd()),
        model_runtime_factory=lambda trace: RouterRecordingRuntime(settings),
        workspace_root=tmp_path / "runs",
    )

    record = harness.run(SCENARIOS[0])
    raw = record.model_dump(mode="json", by_alias=True)
    metrics = aggregate([raw])

    # Testing and Reviewer now consume deterministic evidence, not model calls.
    assert {item["agent"] for item in raw["model_usage"]} == {
        "Product", "Architecture", "Developer", "Security"}
    assert record.llm_calls == 4
    assert len(raw["model_usage"]) == 4
    assert metrics["average_llm_calls"] == 4
    assert set(metrics["latency_by_model"]) == {"qwen3.5:4b", "qwen3.5:9b"}
    assert metrics["structured_output_success"] == 4


def test_evaluation_counts_a_successfully_repaired_local_invocation(tmp_path) -> None:
    settings = Settings(_env_file=None)
    harness = EvaluationHarness(
        quality_mcp=QualityMCP(Path.cwd()),
        model_runtime_factory=lambda trace: RepairRecordingRuntime(settings),
        workspace_root=tmp_path / "runs",
    )

    record = harness.run(SCENARIOS[0])
    metrics = aggregate([record.model_dump(mode="json", by_alias=True)])

    assert record.llm_calls == 5
    assert metrics["structured_output_success"] == 4
    assert metrics["structured_output_failure"] == 1
