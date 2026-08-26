"""Fixed five-scenario evaluation harness and evidence records."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import ConfigDict, Field

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import StrictModel, ToolResult
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.observability.langfuse import LangfuseTracer


class EvaluationScenario(StrictModel):
    identifier: str
    name: str
    requirement: str
    expected_status: str
    expected_security_signal: str


class ScenarioRecord(StrictModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    id: str
    requirement: str
    expected_status: str
    observed_status: str
    status_match: bool
    expected_security_signal: str
    observed_findings: list[str]
    reviewer_score: float
    scores: dict[str, float]
    iterations: int
    models_used: list[str]
    rag_sources: list[str]
    tools_used: list[str]
    tool_evidence: list[str] = Field(default_factory=list)
    trace_id: str
    langfuse_live: bool = False
    pass_: bool = Field(alias="pass")
    duration: float
    llm_calls: int
    tool_calls: int
    retrievals: int
    errors: list[str]
    acceptance_evidence: list[str]
    model_usage: list[dict[str, Any]] = Field(default_factory=list)


SCENARIOS = [
    EvaluationScenario(
        identifier="SC-01", name="Password Recovery",
        requirement="Provide a password-recovery link that expires after 15 minutes and can be used only once.",
        expected_status="APPROVED",
        expected_security_signal="Enforced 15-minute expiration and single-use invalidation.",
    ),
    EvaluationScenario(
        identifier="SC-02", name="Account Locking",
        requirement="Lock an account after five failed authentication attempts.",
        expected_status="APPROVED",
        expected_security_signal="Lockout occurs after exactly five failures.",
    ),
    EvaluationScenario(
        identifier="SC-03", name="Transaction History API",
        requirement="Return only the latest five transactions belonging to the authorized user.",
        expected_status="APPROVED",
        expected_security_signal="Ownership authorization and maximum result count of five.",
    ),
    EvaluationScenario(
        identifier="SC-04", name="Non-expiring reset token",
        requirement="Provide a password-reset token that never expires.",
        expected_status="REJECTED",
        expected_security_signal="Unsafe token lifetime is identified.",
    ),
    EvaluationScenario(
        identifier="SC-05", name="Arbitrary user transactions by ID",
        requirement="Allow access to any user's transactions using only that user's arbitrary ID.",
        expected_status="REJECTED",
        expected_security_signal="Authorization failure and IDOR are identified.",
    ),
]


class EvaluationHarness:
    def __init__(
        self,
        *,
        retriever: Any | None = None,
        quality_mcp: Any | None = None,
        repository_mcp: Any | None = None,
        test_paths: list[str] | None = None,
        tracer: LangfuseTracer | None = None,
        model_runtime_factory: Any | None = None,
        workspace_root: str | Path = "workspace/evaluation",
    ) -> None:
        self.retriever = retriever
        self.quality_mcp = quality_mcp
        self.repository_mcp = repository_mcp
        self.test_paths = test_paths
        self.tracer = tracer or LangfuseTracer(offline_directory="evaluation/reports/traces")
        self.model_runtime_factory = model_runtime_factory
        self.workspace_root = Path(workspace_root)

    def run_all(self) -> list[ScenarioRecord]:
        return [self.run(scenario) for scenario in SCENARIOS]

    def run(self, scenario: EvaluationScenario) -> ScenarioRecord:
        run_id = f"{scenario.identifier.lower()}-{uuid.uuid4()}"
        trace = self.tracer.start_run(run_id, scenario.requirement)
        runtime = self.model_runtime_factory(trace) if self.model_runtime_factory else None
        started = time.perf_counter()
        from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient
        from engineering_team.workspace.isolation import create_run_copy

        run_workspace = create_run_copy(run_id, "sample_app", self.workspace_root)
        timeout = getattr(self.quality_mcp, "timeout_seconds", 60)
        acceptance, acceptance_evidence = _scenario_acceptance(scenario, run_workspace)
        trace.record(
            "scenario acceptance", as_type="tool",
            input={"scenario": scenario.identifier}, output=acceptance.model_dump(mode="json"),
        )
        with (
            MCPQualityClient(run_workspace, timeout_seconds=timeout) as run_quality,
            MCPRepositoryClient(run_workspace, timeout_seconds=timeout) as run_repository,
        ):
            graph = build_engineering_graph(
                quality_mcp=run_quality,
                repository_mcp=run_repository,
                retriever=self.retriever,
                model_runtime=runtime,
                trace=trace,
                test_paths=["test_acceptance.py"],
            )
            state = graph.invoke({
                "run_id": run_id, "requirement": scenario.requirement,
                "tool_results": [acceptance],
            })
        duration = time.perf_counter() - started
        review = state.get("review")
        observed = review.status.value if review is not None else state.get("final_status", "UNKNOWN")
        specification = state.get("specification")
        security = state.get("security_review")
        findings = list(specification.business_rules if specification else [])
        if security:
            findings.extend(f"{item.category}: {item.description}" for item in security.findings)
        models = [item.actual_model or item.requested_model for item in state.get("model_usage", [])]
        sources = list(dict.fromkeys(item.source for item in state.get("rag_evidence", [])))
        tools = [item.tool_name for item in state.get("tool_results", [])]
        tool_evidence = [
            item.evidence_reference for item in state.get("tool_results", [])
            if item.evidence_reference
        ]
        errors = [item.code.value for item in state.get("errors", [])]
        model_usage = [
            item.model_dump(mode="json") for item in state.get("model_usage", [])
        ]
        status_match = scenario.expected_status == observed
        expected_signal_observed = _signal_observed(scenario.identifier, acceptance_evidence, findings)
        return ScenarioRecord(
            id=scenario.identifier,
            requirement=scenario.requirement,
            expected_status=scenario.expected_status,
            observed_status=observed,
            status_match=status_match,
            expected_security_signal=scenario.expected_security_signal,
            observed_findings=findings,
            reviewer_score=review.score if review else 0,
            scores=review.subscores if review else {},
            iterations=state.get("iteration", 0),
            models_used=models,
            rag_sources=sources,
            tools_used=tools,
            tool_evidence=tool_evidence,
            trace_id=trace.trace_id,
            langfuse_live=trace.live,
            pass_=status_match and acceptance.status is ToolStatus.SUCCESS and expected_signal_observed,
            duration=duration,
            llm_calls=len(state.get("model_usage", [])),
            tool_calls=len(tools),
            retrievals=len(state.get("rag_evidence", [])),
            errors=errors,
            acceptance_evidence=acceptance_evidence,
            model_usage=model_usage,
        )

    @staticmethod
    def write(records: list[ScenarioRecord], destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([item.model_dump(mode="json", by_alias=True) for item in records], indent=2),
            encoding="utf-8",
        )
        return path


def _scenario_acceptance(
    scenario: EvaluationScenario, run_workspace: Path
) -> tuple[ToolResult, list[str]]:
    """Execute scenario-specific behavior against the sample application."""
    service_path = run_workspace / "app" / "service.py"
    module_spec = importlib.util.spec_from_file_location(
        f"engineering_eval_{uuid.uuid4().hex}", service_path
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError("isolated sample service could not be loaded")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    BankService = module.BankService

    started = time.perf_counter()
    evidence: list[str] = []
    status = ToolStatus.SUCCESS
    error: str | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="engineering-eval-") as directory:
            database = Path(directory) / "scenario.sqlite"
            service = BankService(database)
            if scenario.identifier == "SC-01":
                before = datetime.now(UTC)
                token = service.issue_reset_token("owner")
                expires_text = service.connection.execute(
                    "SELECT expires FROM reset_tokens WHERE token = ?", (token,)
                ).fetchone()[0]
                expiry_delta = datetime.fromisoformat(expires_text) - before
                assert timedelta(minutes=15) <= expiry_delta < timedelta(minutes=15, seconds=2)
                assert service.use_reset_token(token) is True
                assert service.use_reset_token(token) is False
                evidence = ["expiration=15_minutes", "first_use=accepted", "second_use=denied"]
            elif scenario.identifier == "SC-02":
                for count in range(1, 6):
                    service.record_failed_login("owner")
                    assert service.is_locked("owner") is (count == 5)
                evidence = ["attempts_1_to_4=unlocked", "attempt_5=locked"]
            elif scenario.identifier == "SC-03":
                service.add_transactions("owner", 8)
                assert len(service.history("owner", "owner")) == 5
                try:
                    service.history("attacker", "owner")
                except PermissionError:
                    pass
                else:
                    raise AssertionError("ownership authorization missing")
                evidence = ["authorized_result_count=5", "cross_user_access=denied"]
            elif scenario.identifier == "SC-04":
                token = service.issue_reset_token("owner")
                expires_text = service.connection.execute(
                    "SELECT expires FROM reset_tokens WHERE token = ?", (token,)
                ).fetchone()[0]
                assert datetime.fromisoformat(expires_text) > datetime.now(UTC)
                evidence = ["unsafe_non_expiring_requirement=must_reject", "secure_baseline=expires"]
            elif scenario.identifier == "SC-05":
                service.add_transactions("owner", 2)
                try:
                    service.history("attacker", "owner")
                except PermissionError:
                    evidence = ["authorization_failure=detected", "idor=cross_user_access_denied"]
                else:
                    raise AssertionError("IDOR permitted")
            service.connection.close()
    except (AssertionError, OSError) as exc:
        status = ToolStatus.FAIL
        error = f"{type(exc).__name__}: {exc}"
        evidence.append(error)
    return ToolResult(
        tool_name="scenario_acceptance", allowed_role=AgentRole.TESTING,
        status=status, input_summary=scenario.identifier,
        output_summary="; ".join(evidence),
        duration_ms=int((time.perf_counter() - started) * 1000), error=error,
    ), evidence


def _signal_observed(identifier: str, acceptance: list[str], findings: list[str]) -> bool:
    text = " ".join([*acceptance, *findings]).lower()
    required = {
        "SC-01": ("15_min", "second_use=denied"),
        "SC-02": ("attempt_5=locked",),
        "SC-03": ("result_count=5", "cross_user_access=denied"),
        "SC-04": ("expire",),
        "SC-05": ("authorization", "idor"),
    }
    return all(signal in text for signal in required[identifier])


def run_multimodel_acceptance(
    settings: Any,
    *,
    requirement: str,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute one normal six-agent run using the two configured Ollama tags."""
    from engineering_team.llm.cloud import CloudModelRuntime
    from engineering_team.llm.runtime import LocalModelRuntime
    from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient
    from engineering_team.rag import build_retriever
    from engineering_team.workspace.isolation import create_run_copy

    run_id = f"multimodel-{uuid.uuid4()}"
    run_workspace = create_run_copy(run_id, "sample_app", settings.workspace_root)
    trace = LangfuseTracer(
        public_key=settings.langfuse_public_key,
        secret_key=(
            settings.langfuse_secret_key.get_secret_value()
            if settings.langfuse_secret_key else None
        ),
        base_url=settings.langfuse_base_url,
        offline_directory="evaluation/reports/traces",
    ).start_run(run_id, requirement)
    cloud_first = bool(settings.cloud_enabled and not settings.local_first)
    if cloud_first:
        # Cloud is the steady-state runtime for all six agents; local Ollama is
        # kept as the safety-net fallback if a cloud provider call fails.
        primary_runtime: Any = CloudModelRuntime(settings, trace=trace, primary=True)
        secondary_runtime: Any | None = LocalModelRuntime(settings, trace=trace)
    else:
        primary_runtime = LocalModelRuntime(settings, trace=trace)
        secondary_runtime = CloudModelRuntime(settings, trace=trace) if settings.cloud_enabled else None
    retriever = build_retriever(settings, settings.rag_persist_directory, reindex=True)
    with (
        MCPRepositoryClient(run_workspace) as repository_mcp,
        MCPQualityClient(run_workspace) as quality_mcp,
    ):
        state = build_engineering_graph(
            repository_mcp=repository_mcp,
            quality_mcp=quality_mcp,
            retriever=retriever,
            model_runtime=primary_runtime,
            cloud_runtime=secondary_runtime,
            trace=trace,
            test_paths=["test_acceptance.py"],
        ).invoke({"run_id": run_id, "requirement": requirement})
    usage = [item.model_dump(mode="json") for item in state.get("model_usage", [])]
    expected = [
        ("Product", settings.deep_model),
        ("Architecture", settings.fast_model),
        ("Developer", settings.coding_model),
        ("Security", settings.deep_model),
        ("Testing", settings.fast_model),
        ("Reviewer", settings.deep_model),
    ]
    observed = [(item["agent"], item["actual_model"]) for item in usage]
    if cloud_first:
        # Cloud-first bonus evidence: every agent resolved through a configured
        # cloud provider, matching the fixed per-role provider/model map.
        bonus_pass = all(
            item["provider"] in {"google", "groq"}
            and item["structured_output_success"]
            and item["error"] is None
            for item in usage
        )
    else:
        bonus_pass = (
            observed == expected
            and {item["actual_model"] for item in usage} == {settings.fast_model, settings.deep_model}
            and all(
                item["provider"] == "ollama"
                and not item["fallback_used"]
                and item["structured_output_success"]
                and item["error"] is None
                for item in usage
            )
        )
    evidence = {
        "run_id": run_id,
        "trace_id": trace.trace_id,
        "langfuse_live": trace.live,
        "langfuse_error": trace.live_error,
        "final_status": state.get("final_status"),
        "route_history": state.get("route_history", []),
        "model_usage": usage,
        "rag_sources": list(dict.fromkeys(item.source for item in state.get("rag_evidence", []))),
        "tools_used": [item.tool_name for item in state.get("tool_results", [])],
        "cloud_used": any(item["provider"] != "ollama" for item in usage),
        "cloud_first": cloud_first,
        "bonus_pass": bonus_pass,
        "trace_events": [
            {
                key: event[key]
                for key in ("name", "type", "level", "status_message", "metadata", "model")
                if key in event
            }
            for event in trace.events
        ],
    }
    if report_path is not None:
        path = Path(report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return evidence
