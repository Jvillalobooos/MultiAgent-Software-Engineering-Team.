import json
from collections import deque

import httpx
import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.agents.reviewer import ReviewerAgent
from engineering_team.agents.security import SecurityAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import (
    AgentRole,
    ErrorCode,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import (
    FileMutation,
    ImplementationResult,
    ModelExecutionInfo,
    ReviewerDecision,
    SecurityFinding,
    SecurityReview,
    ToolResult,
)
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.llm.cloud import CloudModelRuntime
from engineering_team.llm.runtime import LocalModelRuntime
from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient
from engineering_team.mcp.repository import RepositoryMCP
from engineering_team.observability.langfuse import LangfuseTracer

CHECKLIST = {key: "PASS" for key in (
    "authentication", "authorization", "input_validation", "sensitive_information",
    "secrets", "injection", "access_control", "idor", "logging", "data_protection",
    "api_abuse", "rate_limiting", "owasp",
)}


class CountingProduct(ProductAgent):
    def __init__(self):
        self.calls = 0
        self.last_envelope = None

    def execute(self, envelope):
        self.calls += 1
        self.last_envelope = envelope
        return super().execute(envelope)


def test_project_capabilities_are_detected_before_product_and_propagated(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    product = CountingProduct()

    result = build_engineering_graph(
        repository_mcp=RepositoryMCP(tmp_path),
        agent_overrides={AgentRole.PRODUCT: product},
    ).invoke({"run_id": "profile", "requirement": "document the behavior"})

    assert product.calls == 1
    assert result["project_capabilities"].ecosystem.value == "python"
    assert product.last_envelope.state_projection["project_capabilities"].fingerprint
    assert result["route_history"][0] == "Product"


def test_unknown_project_stops_before_product_with_capability_error(tmp_path):
    (tmp_path / "README.md").write_text("unknown ecosystem\n", encoding="utf-8")
    product = CountingProduct()

    result = build_engineering_graph(
        repository_mcp=RepositoryMCP(tmp_path),
        agent_overrides={AgentRole.PRODUCT: product},
    ).invoke({"run_id": "unknown", "requirement": "change behavior"})

    assert product.calls == 0
    assert result["final_status"] == "INCOMPLETE"
    assert result["route_history"] == ["INCOMPLETE"]
    assert result["errors"][-1].code is ErrorCode.PROJECT_CAPABILITY_ERROR


def test_graph_passes_only_the_validated_profile_fingerprint_to_quality(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")

    class FingerprintQuality(PassingQuality):
        def __init__(self):
            self.fingerprints = []

        def run_tests(self, role, paths=None, profile_fingerprint=None):
            self.fingerprints.append(profile_fingerprint)
            return super().run_tests(role, paths)

    quality = FingerprintQuality()
    result = build_engineering_graph(
        repository_mcp=RepositoryMCP(tmp_path),
        quality_mcp=quality,
    ).invoke({"run_id": "quality-profile", "requirement": "document behavior"})

    assert quality.fingerprints == [result["project_capabilities"].fingerprint]


class ApplyingDeveloper:
    def execute(self, envelope):
        return ImplementationResult(
            action_mode="PROPOSED", changed_files=["app/email.py"], diff="proposed email change",
            evidence=["mcp://repository/read_file#app/email.py"], validation_result="proposal",
            mutations=[FileMutation(
                path="app/email.py", operation="update",
                content="def change_email(current_password, email):\n    return email\n",
            )],
        )


class PassingQuality:
    def run_tests(self, role, paths=None):
        return ToolResult(
            tool_name="run_tests", allowed_role=role, status=ToolStatus.SUCCESS,
            input_summary="safe", output_summary="1 passed", duration_ms=1,
            evidence_reference="mcp://quality/run_tests",
        )


class ProposedDeveloper:
    def execute(self, envelope):
        return ImplementationResult(
            action_mode="PROPOSED", changed_files=["app/email.py"], diff="PROPOSED\n+change",
            evidence=["mcp://repository/read_file#app/email.py"], validation_result="proposal",
        )


class CountingSecurity(SecurityAgent):
    def __init__(self):
        self.calls = 0

    def execute(self, envelope):
        self.calls += 1
        return super().execute(envelope)


class CountingTesting:
    def __init__(self):
        self.calls = 0

    def execute(self, envelope):
        self.calls += 1
        from engineering_team.agents.testing import TestingAgent
        return TestingAgent().execute(envelope)


class CapturingTesting:
    def __init__(self):
        self.envelopes = []

    def execute(self, envelope):
        self.envelopes.append(envelope)
        from engineering_team.agents.testing import TestingAgent
        return TestingAgent().execute(envelope)


def test_testing_receives_at_most_one_validated_native_test_example(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_existing.py").write_text(
        "def test_existing():\n    assert True\n", encoding="utf-8"
    )
    testing = CapturingTesting()

    result = build_engineering_graph(
        repository_mcp=RepositoryMCP(tmp_path),
        agent_overrides={AgentRole.TESTING: testing},
    ).invoke({"run_id": "test-example", "requirement": "document behavior"})

    examples = [
        item for item in testing.envelopes[0].tool_results
        if item.tool_name == "read_test_file"
    ]
    assert len(examples) == 1
    assert examples[0].input_summary == "path=tests/test_existing.py"
    assert "def test_existing" in examples[0].output_summary
    assert any(item.tool_name == "read_test_file" for item in result["tool_results"])


def test_graph_rejects_a_cross_ecosystem_testing_mutation_before_write(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest run"}}\n', encoding="utf-8"
    )

    def handler(request):
        payload = json.loads(request.content)
        properties = set(payload["format"]["properties"])
        if properties == {"mutations", "no_mutation_reason", "blocker"}:
            response = {"mutations": [], "no_mutation_reason": "no source change required"}
        elif properties == {"test_mutations", "no_mutation_reason"}:
            response = {
                "test_mutations": [{
                    "path": "tests/test_wrong.py",
                    "operation": "create",
                    "content": "def test_wrong():\n    assert True\n",
                }],
                "no_mutation_reason": None,
            }
        else:
            raw = payload["prompt"].split("Candidate artifact: ", 1)[1]
            response, _ = json.JSONDecoder().raw_decode(raw)
        return httpx.Response(
            200, json={"model": payload["model"], "response": json.dumps(response)}
        )

    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = build_engineering_graph(
        repository_mcp=RepositoryMCP(tmp_path),
        model_runtime=runtime,
    ).invoke({"run_id": "wrong-native-test", "requirement": "document behavior"})

    assert not (tmp_path / "tests" / "test_wrong.py").exists()
    assert any("non-native test mutation path" in error.detail for error in result["errors"])


class CountingReviewer(ReviewerAgent):
    def __init__(self):
        self.calls = 0

    def execute(self, envelope):
        self.calls += 1
        return super().execute(envelope)


def rejected(category, target):
    return ReviewerDecision(
        status=ReviewerStatus.REJECTED, score=40, subscores={}, problems=["fix"],
        reason="fix", remediation_category=category, return_to=target, confidence=0.9,
    )


class ScriptedReviewer(ReviewerAgent):
    def __init__(self, decisions):
        self.decisions = deque(decisions)
        self.calls = 0

    def execute(self, envelope):
        self.calls += 1
        return self.decisions.popleft() if self.decisions else super().execute(envelope)


@pytest.mark.parametrize(
    ("decision", "expected_tail"),
    [
        (rejected(RemediationCategory.ARCHITECTURE, RouteTarget.ARCHITECTURE),
         ["Architecture", "Developer", "Security", "Testing", "Reviewer"]),
        (rejected(RemediationCategory.IMPLEMENTATION, RouteTarget.DEVELOPER),
         ["Developer", "Security", "Testing", "Reviewer"]),
        (rejected(RemediationCategory.SECURITY, RouteTarget.DEVELOPER),
         ["Developer", "Security", "Testing", "Reviewer"]),
        (rejected(RemediationCategory.TESTING, RouteTarget.DEVELOPER),
         ["Developer", "Testing", "Reviewer"]),
    ],
)
def test_reviewer_remediation_chains_return_through_required_validation(decision, expected_tail):
    reviewer = ScriptedReviewer([decision])
    graph = build_engineering_graph(agent_overrides={AgentRole.REVIEWER: reviewer})

    result = graph.invoke({"run_id": "remediation", "requirement": "safe bounded change"})

    first_reviewer = result["route_history"].index("Reviewer")
    assert result["route_history"][first_reviewer + 1 : first_reviewer + 1 + len(expected_tail)] == expected_tail
    assert result["iteration"] == 1
    assert result["final_status"] == "APPROVED"


def test_third_rejected_cycle_stops_without_a_fourth_cycle():
    decision = rejected(RemediationCategory.IMPLEMENTATION, RouteTarget.DEVELOPER)
    reviewer = ScriptedReviewer([decision, decision, decision, decision])
    graph = build_engineering_graph(agent_overrides={AgentRole.REVIEWER: reviewer})

    result = graph.invoke({"run_id": "max", "requirement": "bounded change"})

    assert result["iteration"] == 3
    assert result["human_review_required"] is False
    assert result["final_status"] == "INCOMPLETE"
    assert reviewer.calls == 3


class CriticalSecurity(SecurityAgent):
    def execute(self, envelope):
        finding = SecurityFinding(
            category="secrets", severity=SecuritySeverity.CRITICAL,
            description="critical exposure", affected_evidence=["diff"],
            recommendation="human containment", sources=[],
        )
        return SecurityReview(
            status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.CRITICAL,
            findings=[finding], recommendations=[finding.recommendation], sources=[],
            checklist=CHECKLIST,
            requires_hitl=True,
        )


def test_critical_security_finishes_incomplete_before_reviewer():
    reviewer = ScriptedReviewer([])
    graph = build_engineering_graph(
        agent_overrides={AgentRole.SECURITY: CriticalSecurity(), AgentRole.REVIEWER: reviewer}
    )

    result = graph.invoke({"run_id": "critical", "requirement": "change"})

    assert result["route_history"][-1] == "INCOMPLETE"
    assert result["final_status"] == "INCOMPLETE"
    assert reviewer.calls == 0


class FailThenPassQuality:
    def __init__(self):
        self.calls = 0

    def run_tests(self, role, paths=None):
        self.calls += 1
        status = ToolStatus.FAIL if self.calls == 1 else ToolStatus.SUCCESS
        return ToolResult(
            tool_name="run_tests", allowed_role=role, status=status, input_summary="safe",
            output_summary="1 failed" if status is ToolStatus.FAIL else "1 passed", duration_ms=1,
        )


def test_failed_mcp_test_result_changes_reviewer_route_and_is_remediated():
    quality = FailThenPassQuality()
    result = build_engineering_graph(quality_mcp=quality).invoke(
        {"run_id": "mcp", "requirement": "safe change"}
    )

    assert result["tool_results"][0].status is ToolStatus.FAIL
    assert result["test_results"][0].status is ToolStatus.FAIL
    assert result["review"].status is ReviewerStatus.APPROVED
    assert result["iteration"] == 1
    assert result["route_history"].count("Reviewer") == 2
    assert result["route_history"][-4:] == ["Developer", "Testing", "Reviewer", "FinalReport"]


def test_real_mcp_protocol_failure_changes_reviewer_route_and_is_remediated(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "test_protocol_route.py").write_text(
        "from pathlib import Path\n"
        "def test_fail_once():\n"
        "    marker = Path('.mcp-remediated')\n"
        "    if not marker.exists():\n"
        "        marker.write_text('remediated', encoding='utf-8')\n"
        "        assert False\n",
        encoding="utf-8",
    )
    trace = LangfuseTracer(offline_directory=tmp_path / "traces").start_run(
        "real-mcp", "safe bounded change"
    )

    with MCPQualityClient(tmp_path) as quality:
        result = build_engineering_graph(quality_mcp=quality, trace=trace).invoke(
            {"run_id": "real-mcp", "requirement": "safe bounded change"}
        )

    failed = [item for item in result["tool_results"] if item.tool_name == "run_tests"]
    assert failed[0].status is ToolStatus.FAIL
    assert result["test_results"][0].status is ToolStatus.FAIL
    first_reviewer = result["route_history"].index("Reviewer")
    assert result["route_history"][first_reviewer + 1 : first_reviewer + 4] == [
        "Developer", "Testing", "Reviewer"
    ]
    assert result["final_status"] == "APPROVED"
    protocol_events = [
        event for event in trace.events
        if event["name"] == "MCP call" and event["metadata"].get("transport") == "stdio"
    ]
    assert protocol_events
    assert all(event["metadata"]["protocol_version"] for event in protocol_events)
    assert any(item.code is ErrorCode.TOOL_ERROR for item in result["errors"])
    assert any(event["name"] == "TOOL_ERROR" for event in trace.events)


def test_required_repository_mcp_unavailable_is_recorded_and_cannot_approve(tmp_path):
    missing_root = tmp_path / "missing-workspace"
    repository = MCPRepositoryClient(missing_root, timeout_seconds=2)
    trace = LangfuseTracer(offline_directory=tmp_path / "traces").start_run(
        "mcp-unavailable", "safe bounded change"
    )

    try:
        result = build_engineering_graph(repository_mcp=repository, trace=trace).invoke(
            {"run_id": "mcp-unavailable", "requirement": "safe bounded change"}
        )
    finally:
        repository.close()

    assert any(item.status is ToolStatus.UNAVAILABLE for item in result["tool_results"])
    assert any(item.code is ErrorCode.MCP_ERROR for item in result["errors"])
    assert result["final_status"] == "INCOMPLETE"
    assert result.get("review") is None
    assert any(event["name"] == "MCP_ERROR" for event in trace.events)
    assert not any(item.fallback_used for item in result.get("model_usage", []))


def test_workflow_searches_and_reads_relevant_repository_files_for_developer(tmp_path):
    (tmp_path / "README.md").write_text("general notes\n", encoding="utf-8")
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "misc.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "transactions.py").write_text(
        "def transaction_history(connection, owner_id):\n"
        "    return connection.execute('SELECT * FROM transactions').fetchall()\n",
        encoding="utf-8",
    )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "developer-relevance",
            "requirement": (
                "Return only the latest five transactions belonging to the authorized user."
            ),
        })

    developer_tools = [
        item for item in result["tool_results"]
        if item.allowed_role is AgentRole.DEVELOPER
    ]
    assert "search_code" in [item.tool_name for item in developer_tools]
    assert "read_file" in [item.tool_name for item in developer_tools]
    assert result["implementation"].changed_files == ["app/transactions.py"]
    assert "transaction_history" in result["implementation"].diff


def test_product_and_architecture_persist_decision_documents_in_run_workspace(tmp_path):
    workspace = tmp_path / "run"
    workspace.mkdir()

    build_engineering_graph().invoke({
        "run_id": "decision-documents",
        "requirement": "allow a user to change their password safely",
        "repository_context": {"workspace": str(workspace)},
    })

    product_document = workspace / "docs" / "decisions" / "product-specification.md"
    architecture_document = workspace / "docs" / "decisions" / "architecture-decisions.md"
    assert "allow a user to change their password safely" in product_document.read_text(encoding="utf-8")
    assert "Decisions" in architecture_document.read_text(encoding="utf-8")


def test_developer_never_uses_generated_trace_as_implementation_target(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def change_email(current_password, new_email):\n    return new_email\n", encoding="utf-8"
    )
    trace = tmp_path / "evaluation" / "reports" / "traces"
    trace.mkdir(parents=True)
    requirement = "change email after confirming the current password"
    (trace / "old-run.json").write_text(requirement, encoding="utf-8")

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "trace-noise", "requirement": requirement,
        })

    assert result["implementation"].changed_files == ["app/service.py"]
    assert "evaluation/reports/traces/old-run.json" not in result["implementation"].diff


def test_generated_search_hit_does_not_remove_source_fallback(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text("def execute():\n    return True\n", encoding="utf-8")
    trace = tmp_path / "evaluation" / "reports"
    trace.mkdir(parents=True)
    (trace / "old-run.json").write_text("authorize transaction history", encoding="utf-8")

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "search-fallback", "requirement": "authorize transaction history",
        })

    assert result["implementation"].changed_files == ["app/service.py"]


def test_structural_expansion_reaches_python_relative_import_target(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        "from .service import apply_update\n\n\n"
        "def entrypoint(payload):\n    return apply_update(payload)\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "service.py").write_text(
        "def apply_update(payload):\n"
        "    if not payload.get('secreto'):\n"
        "        raise ValueError('secreto requerido')\n"
        "    return payload\n",
        encoding="utf-8",
    )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "structural-python",
            "requirement": "Asegura que el modulo de entrada delegue la logica de negocio antes de responder.",
        })

    assert "app/service.py" in result["implementation"].changed_files


def test_structural_expansion_reaches_typescript_relative_import_target(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}),
        encoding="utf-8",
    )
    (tmp_path / "src" / "routes").mkdir(parents=True)
    (tmp_path / "src" / "domain").mkdir(parents=True)
    (tmp_path / "src" / "routes" / "account.ts").write_text(
        "import { promote } from \"../domain/account-manager\";\n\n"
        "export function handleRequest(payload) {\n  return promote(payload);\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "domain" / "account-manager.ts").write_text(
        "export function promote(payload) {\n"
        "  if (!payload.aprobado) {\n"
        "    throw new Error('se requiere aprobacion');\n"
        "  }\n  return payload;\n}\n",
        encoding="utf-8",
    )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "structural-typescript",
            "requirement": "Aumenta el nivel de acceso solo cuando existe autorizacion previa.",
        })

    assert "src/domain/account-manager.ts" in result["implementation"].changed_files


def test_structural_expansion_reaches_java_like_dotted_import_target(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    entry = tmp_path / "src" / "main" / "java" / "com" / "example" / "api"
    impl = tmp_path / "src" / "main" / "java" / "com" / "example" / "domain"
    entry.mkdir(parents=True)
    impl.mkdir(parents=True)
    (entry / "AccountController.java").write_text(
        "package com.example.api;\n\n"
        "import com.example.domain.AccountService;\n\n"
        "class AccountController {\n"
        "    void handle() { new AccountService().run(); }\n"
        "}\n",
        encoding="utf-8",
    )
    (impl / "AccountService.java").write_text(
        "package com.example.domain;\n\n"
        "class AccountService {\n"
        "    void run() { if (!authorized()) throw new RuntimeException('denied'); }\n"
        "    boolean authorized() { return false; }\n"
        "}\n",
        encoding="utf-8",
    )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "structural-java",
            "requirement": "Bloquea la peticion entrante hasta validar el permiso correspondiente.",
        })

    assert any(
        path.endswith("com/example/domain/AccountService.java")
        for path in result["implementation"].changed_files
    )


def test_low_information_package_marker_never_outranks_real_source(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "service.py").write_text(
        "def apply(payload):\n"
        "    if not payload.get('clave'):\n"
        "        raise ValueError('clave requerida')\n"
        "    return payload\n",
        encoding="utf-8",
    )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(repository_mcp=repository).invoke({
            "run_id": "low-info-marker",
            "requirement": "Rechaza cualquier solicitud sin credencial valida.",
        })

    assert result["implementation"].changed_files[0] == "app/service.py"


def test_adaptive_remediation_expands_to_new_structural_evidence(tmp_path):
    """Simulate a remediation cycle (iteration=1) that starts from a prior,
    insufficient inspection (only the entrypoint was read). The bounded
    remediation expansion must deterministically discover the referenced
    implementation module before the Developer model is invoked again --
    proving cycle 1 introduces materially new repository evidence, not a
    repeat of the same insufficient context."""
    (tmp_path / "app").mkdir()
    main_content = (
        "from .service import apply_update\n\n\n"
        "def entrypoint(payload):\n    return apply_update(payload)\n"
    )
    (tmp_path / "app" / "main.py").write_text(main_content, encoding="utf-8")
    (tmp_path / "app" / "service.py").write_text(
        "def apply_update(payload):\n"
        "    if not payload.get('secreto'):\n"
        "        raise ValueError('secreto requerido')\n"
        "    return payload\n",
        encoding="utf-8",
    )
    developer_requests: list[dict] = []

    def handler(request):
        payload = json.loads(request.content)
        properties = set(payload["format"]["properties"])
        if properties == {"mutations", "no_mutation_reason", "blocker"}:
            developer_requests.append(payload)
            response = {"mutations": [], "no_mutation_reason": "insufficient implementation context"}
        else:
            raw = payload["prompt"].split("Candidate artifact: ", 1)[1]
            response, _ = json.JSONDecoder().raw_decode(raw)
        return httpx.Response(200, json={"model": payload["model"], "response": json.dumps(response)})

    runtime = LocalModelRuntime(
        Settings(_env_file=None), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    seeded_read = ToolResult(
        tool_name="read_file", allowed_role=AgentRole.DEVELOPER, status=ToolStatus.SUCCESS,
        input_summary="path=app/main.py", output_summary=main_content,
        duration_ms=1, evidence_reference="mcp://repository/read_file",
    )
    with MCPRepositoryClient(tmp_path) as repository:
        build_engineering_graph(repository_mcp=repository, model_runtime=runtime).invoke({
            "run_id": "adaptive-remediation",
            "requirement": "Asegura que el modulo de entrada delegue la logica de negocio antes de responder.",
            "repository_context": {"implementation_required": True},
            "iteration": 1,
            "remediation_request": "insufficient implementation context",
            "tool_results": [seeded_read],
        })

    assert developer_requests
    first_request_prompt = developer_requests[0]["prompt"]
    assert "app/main.py" in first_request_prompt
    assert "app/service.py" in first_request_prompt


def test_no_progress_skips_redundant_call_after_structural_frontier_is_exhausted(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text(
        "from .service import apply_update\n\n\n"
        "def entrypoint(payload):\n    return apply_update(payload)\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "service.py").write_text(
        "def apply_update(payload):\n"
        "    if not payload.get('secreto'):\n"
        "        raise ValueError('secreto requerido')\n"
        "    return payload\n",
        encoding="utf-8",
    )

    class CountingRuntime:
        def __init__(self):
            self.attempts = []
            self.developer_calls = 0

        def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
            if role is AgentRole.DEVELOPER:
                self.developer_calls += 1
            return candidate, ModelExecutionInfo(
                agent=role, provider="ollama", requested_model="test", actual_model="test",
                model_profile="LOCAL", latency_ms=1, structured_output_success=True,
            )

    runtime = CountingRuntime()
    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository, model_runtime=runtime,
        ).invoke({
            "run_id": "no-progress-exhausted",
            "requirement": "Asegura que el modulo de entrada delegue la logica de negocio antes de responder.",
            "repository_context": {"implementation_required": True},
        })

    # A non-actionable remediation cycle (zero mutations, no structured blocker) is
    # classified and routed to HITL immediately instead of burning further iterations.
    assert runtime.developer_calls == 2
    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert any(
        error.code is ErrorCode.DEVELOPER_REMEDIATION_EXHAUSTED for error in result["errors"]
    )
    assert any(
        item.tool_name == "read_file" and item.input_summary == "path=app/service.py"
        for item in result["tool_results"]
    )


def test_repeated_no_progress_skips_the_third_developer_model_call(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def change_email(current_password, new_email):\n    return new_email\n", encoding="utf-8"
    )

    class CountingRuntime:
        def __init__(self):
            self.attempts = []
            self.developer_calls = 0

        def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
            if role is AgentRole.DEVELOPER:
                self.developer_calls += 1
            return candidate, ModelExecutionInfo(
                agent=role, provider="ollama", requested_model="test", actual_model="test",
                model_profile="LOCAL", latency_ms=1, structured_output_success=True,
            )

    runtime = CountingRuntime()
    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository, model_runtime=runtime,
        ).invoke({
            "run_id": "no-progress", "requirement": "change email after confirming current password",
            "repository_context": {"implementation_required": True},
        })

    assert runtime.developer_calls == 2
    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert any(
        error.code is ErrorCode.DEVELOPER_REMEDIATION_EXHAUSTED for error in result["errors"]
    )


def test_graph_derives_applied_only_from_mcp_write_and_real_diff(tmp_path):
    (tmp_path / "app").mkdir()
    original = "def change_email(current_password, email):\n    raise NotImplementedError\n"
    (tmp_path / "app" / "email.py").write_text(original, encoding="utf-8")

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository, quality_mcp=PassingQuality(),
            agent_overrides={AgentRole.DEVELOPER: ApplyingDeveloper()},
        ).invoke({
            "run_id": "applied", "requirement": "change email after current password confirmation",
            "repository_context": {"implementation_required": True},
        })

    implementation = result["implementation"]
    assert implementation.action_mode.value == "APPLIED"
    assert "NotImplementedError" in implementation.diff
    assert any(item.tool_name == "update_file" and item.status is ToolStatus.SUCCESS for item in result["tool_results"])
    assert any(item.tool_name == "get_diff" and item.output_summary for item in result["tool_results"])
    assert result["test_results"][-1].generated_tests == []
    assert result["final_status"] == "INCOMPLETE"


def test_real_developer_runtime_plan_applies_inspected_source_via_mcp(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "email.py").write_text(
        "def change_email(current_password, new_email):\n    raise NotImplementedError\n",
        encoding="utf-8",
    )
    developer_requests: list[dict] = []

    def handler(request):
        payload = json.loads(request.content)
        properties = set(payload["format"]["properties"])
        if properties == {"mutations", "no_mutation_reason", "blocker"}:
            developer_requests.append(payload)
            response = {
                "mutations": [{
                    "path": "app/email.py",
                    "operation": "update",
                    "content": (
                        "def change_email(current_password, expected_password, new_email):\n"
                        "    if current_password != expected_password:\n"
                        "        raise ValueError('current password required')\n"
                        "    return new_email\n"
                    ),
                }],
                "no_mutation_reason": None,
            }
        else:
            raw = payload["prompt"].split("Candidate artifact: ", 1)[1]
            response, _ = json.JSONDecoder().raw_decode(raw)
        return httpx.Response(200, json={"model": payload["model"], "response": json.dumps(response)})

    runtime = LocalModelRuntime(
        Settings(_env_file=None), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository,
            quality_mcp=PassingQuality(),
            model_runtime=runtime,
        ).invoke({
            "run_id": "real-developer-plan",
            "requirement": "change email after confirming the current password",
            "repository_context": {"implementation_required": True},
        })

    assert developer_requests
    assert result["implementation"].action_mode.value == "APPLIED"
    assert any(item.tool_name == "update_file" and item.status is ToolStatus.SUCCESS for item in result["tool_results"])
    assert any(item.tool_name == "get_diff" and item.output_summary for item in result["tool_results"])
    assert result["route_history"][:6] == [
        "Product", "Architecture", "Developer", "Security", "Testing", "Reviewer",
    ]


def test_unapplied_developer_fast_fails_without_security_testing_or_reviewer_work():
    security = CountingSecurity()
    testing = CountingTesting()
    reviewer = CountingReviewer()
    result = build_engineering_graph(agent_overrides={
        AgentRole.DEVELOPER: ProposedDeveloper(),
        AgentRole.SECURITY: security,
        AgentRole.TESTING: testing,
        AgentRole.REVIEWER: reviewer,
    }).invoke({
        "run_id": "fast-fail", "requirement": "change email",
        "repository_context": {"implementation_required": True},
    })

    assert security.calls == 0
    assert testing.calls == 0
    assert reviewer.calls == 0
    assert result["iteration"] == 3
    assert result["final_status"] == "INCOMPLETE"


def test_uninspected_developer_mutation_is_not_written_or_approved(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")

    class UninspectedDeveloper:
        def execute(self, envelope):
            return ImplementationResult(
                action_mode="PROPOSED", changed_files=["app/unknown.py"], diff="PROPOSED\n+change",
                evidence=["mcp://repository/list_files"], validation_result="proposal",
                mutations=[FileMutation(path="app/unknown.py", operation="update", content="value = 1\n")],
            )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository,
            agent_overrides={AgentRole.DEVELOPER: UninspectedDeveloper()},
        ).invoke({
            "run_id": "uninspected", "requirement": "change email",
            "repository_context": {"implementation_required": True},
        })

    assert not (tmp_path / "app" / "unknown.py").exists()
    assert any("uninspected mutation path" in error.detail for error in result["errors"])


def test_destructive_python_update_is_rejected_before_repository_write(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'preservation-fixture'\n", encoding="utf-8"
    )
    (tmp_path / "app").mkdir()
    source = tmp_path / "app" / "main.py"
    original = (
        "def existing_behavior():\n    return 'available'\n\n"
        "def requested_behavior():\n    return 'old'\n"
    )
    source.write_text(original, encoding="utf-8")

    class DestructiveDeveloper:
        def execute(self, envelope):
            return ImplementationResult(
                action_mode="PROPOSED",
                changed_files=["app/main.py"],
                diff="PROPOSED\nreplace module",
                evidence=["mcp://repository/read_file#app/main.py"],
                validation_result="proposal",
                mutations=[FileMutation(
                    path="app/main.py",
                    operation="update",
                    content="def requested_behavior():\n    return 'new'\n",
                )],
            )

    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository,
            agent_overrides={AgentRole.DEVELOPER: DestructiveDeveloper()},
        ).invoke({
            "run_id": "preservation-guard",
            "requirement": (
                "update requested_behavior in app/main.py while preserving existing_behavior"
            ),
            "repository_context": {"implementation_required": True},
        })

    assert source.read_text(encoding="utf-8") == original
    assert not any(
        item.tool_name == "update_file" and item.status is ToolStatus.SUCCESS
        for item in result["tool_results"]
    )
    assert any(
        "removed Python boundaries" in error.detail
        and "function:existing_behavior" in error.detail
        for error in result["errors"]
    ), [error.detail for error in result["errors"]]


def test_generated_test_is_written_and_executed_in_isolated_workspace(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "email.py").write_text(
        "def change_email(current_password, email):\n    raise NotImplementedError\n",
        encoding="utf-8",
    )

    def handler(request):
        payload = json.loads(request.content)
        properties = set(payload["format"]["properties"])
        if properties == {"mutations", "no_mutation_reason", "blocker"}:
            response = {
                "mutations": [{
                    "path": "app/email.py",
                    "operation": "update",
                    "content": (
                        "def change_email(current_password, email):\n"
                        "    return email\n"
                    ),
                }],
                "no_mutation_reason": None,
            }
        elif properties == {"test_mutations", "no_mutation_reason"}:
            response = {
                "test_mutations": [{
                    "path": "tests/test_email_change.py",
                    "operation": "create",
                    "content": (
                        "from app.email import change_email\n\n\n"
                        "def test_email_change_returns_requested_value():\n"
                        "    assert change_email('current', 'new@example.test') == "
                        "'new@example.test'\n"
                    ),
                }],
                "no_mutation_reason": None,
            }
        else:
            raw = payload["prompt"].split("Candidate artifact: ", 1)[1]
            response, _ = json.JSONDecoder().raw_decode(raw)
        return httpx.Response(
            200, json={"model": payload["model"], "response": json.dumps(response)}
        )

    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with (
        MCPRepositoryClient(tmp_path) as repository,
        MCPQualityClient(tmp_path) as quality,
    ):
        result = build_engineering_graph(
                repository_mcp=repository, quality_mcp=quality,
                agent_overrides={AgentRole.DEVELOPER: ApplyingDeveloper()},
                model_runtime=runtime,
        ).invoke({
            "run_id": "generated-test", "requirement": "return the requested email change",
            "repository_context": {"implementation_required": True},
        })

    test_result = result["test_results"][-1]
    assert test_result.generated_tests == ["tests/test_email_change.py"]
    assert test_result.status is ToolStatus.SUCCESS
    generated_source = (tmp_path / "tests" / "test_email_change.py").read_text(
        encoding="utf-8"
    )
    assert "from app.email import change_email" in generated_source
    assert "read_text" not in generated_source
    assert "initial_hash_value" not in generated_source


def test_failed_quality_evidence_causes_second_developer_mutation_and_approval(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'causal-counter-fixture'\n", encoding="utf-8"
    )
    source = tmp_path / "counter.py"
    source.write_text(
        "class Counter:\n"
        "    def increment(self):\n"
        "        raise NotImplementedError\n",
        encoding="utf-8",
    )
    developer_prompts: list[str] = []
    testing_calls = 0

    def handler(request):
        nonlocal testing_calls
        payload = json.loads(request.content)
        properties = set(payload["format"]["properties"])
        if properties == {"mutations", "no_mutation_reason", "blocker"}:
            developer_prompts.append(payload["prompt"])
            first_cycle = len(developer_prompts) == 1
            content = (
                "class Counter:\n"
                "    def increment(self):\n"
                "        self.value += 1\n"
                "        return self.value\n"
                if first_cycle
                else
                "class Counter:\n"
                "    def __init__(self):\n"
                "        self.value = 0\n\n"
                "    def increment(self):\n"
                "        self.value += 1\n"
                "        return self.value\n"
            )
            response = {
                "mutations": [{
                    "path": "counter.py", "operation": "update", "content": content,
                }],
                "no_mutation_reason": None,
            }
        elif properties == {"test_mutations", "no_mutation_reason"}:
            testing_calls += 1
            response = {
                "test_mutations": [{
                    "path": "tests/test_counter_behavior.py",
                    "operation": "create" if testing_calls == 1 else "update",
                    "content": (
                        "from counter import Counter\n\n\n"
                        "def test_increment_advances_persisted_instance_state():\n"
                        "    counter = Counter()\n"
                        "    assert counter.increment() == 1\n"
                        "    assert counter.increment() == 2\n"
                    ),
                }],
                "no_mutation_reason": None,
            }
        else:
            raw = payload["prompt"].split("Candidate artifact: ", 1)[1]
            response, _ = json.JSONDecoder().raw_decode(raw)
        return httpx.Response(
            200, json={"model": payload["model"], "response": json.dumps(response)}
        )

    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with (
        MCPRepositoryClient(tmp_path) as repository,
        MCPQualityClient(tmp_path) as quality,
    ):
        result = build_engineering_graph(
            repository_mcp=repository,
            quality_mcp=quality,
            model_runtime=runtime,
        ).invoke({
            "run_id": "causal-remediation-integration",
            "requirement": "make Counter.increment in counter.py advance state on every call",
            "repository_context": {"implementation_required": True},
        })

    run_tests = [
        item for item in result["tool_results"] if item.tool_name == "run_tests"
    ]
    repository_writes = [
        item for item in result["tool_results"]
        if item.tool_name == "update_file"
        and item.allowed_role is AgentRole.DEVELOPER
        and item.status is ToolStatus.SUCCESS
    ]
    diffs = [
        item for item in result["tool_results"]
        if item.tool_name == "get_diff" and item.status is ToolStatus.SUCCESS
    ]

    assert result["final_status"] == "APPROVED", {
        "route": result["route_history"],
        "errors": [error.detail for error in result["errors"]],
        "developer_prompts": len(developer_prompts),
        "testing_calls": testing_calls,
        "run_tests": [
            (item.status.value, item.output_summary[-600:]) for item in run_tests
        ],
        "repository_writes": len(repository_writes),
        "diffs": len(diffs),
    }


class NonActionableCloudDeveloper:
    """CLOUD_FIRST primary: real enrichment for every role, always non-actionable for Developer."""

    def __init__(self):
        self.attempts = []
        self.testing_calls = 0

    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
        info = ModelExecutionInfo(
            agent=role, provider="google", requested_model="gemini-3.7-flash",
            actual_model="gemini-3.7-flash", model_profile="CLOUD_PRIMARY",
            fallback_used=mode == "fallback", fallback_reason=fallback_reason,
            latency_ms=1, structured_output_success=True,
        )
        self.attempts.append(info)
        if role is AgentRole.DEVELOPER:
            return candidate.model_copy(update={"mutations": [], "blocker": None}), info
        if role is AgentRole.TESTING:
            self.testing_calls += 1
            mutation = FileMutation(
                path="tests/test_counter_behavior.py",
                operation="create" if self.testing_calls == 1 else "update",
                content=(
                    "from counter import Counter\n\n\n"
                    "def test_increment_advances_persisted_instance_state():\n"
                    "    counter = Counter()\n"
                    "    assert counter.increment() == 1\n"
                    "    assert counter.increment() == 2\n"
                ),
            )
            artifact = candidate.model_copy(update={
                "test_mutations": [mutation], "generated_tests": [mutation.path],
            })
            return artifact, info
        return candidate, info


def test_cloud_first_non_actionable_developer_falls_back_to_local_and_approves(tmp_path):
    """Proves the CLOUD_FIRST + local-fallback + non-actionable-remediation mechanism
    end-to-end: cloud is tried first for every role; only Developer's non-actionable
    remediation cycles reach the local fallback, and the run still ends APPROVED."""
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname = 'causal-counter-fixture'\n", encoding="utf-8"
    )
    source = tmp_path / "counter.py"
    source.write_text(
        "class Counter:\n"
        "    def increment(self):\n"
        "        raise NotImplementedError\n",
        encoding="utf-8",
    )
    developer_prompts: list[str] = []
    testing_calls = 0

    def handler(request):
        nonlocal testing_calls
        payload = json.loads(request.content)
        properties = set(payload["format"]["properties"])
        if properties == {"mutations", "no_mutation_reason", "blocker"}:
            developer_prompts.append(payload["prompt"])
            first_cycle = len(developer_prompts) == 1
            content = (
                "class Counter:\n"
                "    def increment(self):\n"
                "        self.value += 1\n"
                "        return self.value\n"
                if first_cycle
                else
                "class Counter:\n"
                "    def __init__(self):\n"
                "        self.value = 0\n\n"
                "    def increment(self):\n"
                "        self.value += 1\n"
                "        return self.value\n"
            )
            response = {
                "mutations": [{
                    "path": "counter.py", "operation": "update", "content": content,
                }],
                "no_mutation_reason": None,
            }
        elif properties == {"test_mutations", "no_mutation_reason"}:
            testing_calls += 1
            response = {
                "test_mutations": [{
                    "path": "tests/test_counter_behavior.py",
                    "operation": "create" if testing_calls == 1 else "update",
                    "content": (
                        "from counter import Counter\n\n\n"
                        "def test_increment_advances_persisted_instance_state():\n"
                        "    counter = Counter()\n"
                        "    assert counter.increment() == 1\n"
                        "    assert counter.increment() == 2\n"
                    ),
                }],
                "no_mutation_reason": None,
            }
        else:
            raw = payload["prompt"].split("Candidate artifact: ", 1)[1]
            response, _ = json.JSONDecoder().raw_decode(raw)
        return httpx.Response(
            200, json={"model": payload["model"], "response": json.dumps(response)}
        )

    local_fallback = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    cloud_primary = NonActionableCloudDeveloper()
    with (
        MCPRepositoryClient(tmp_path) as repository,
        MCPQualityClient(tmp_path) as quality,
    ):
        result = build_engineering_graph(
            repository_mcp=repository,
            quality_mcp=quality,
            model_runtime=local_fallback,
            cloud_runtime=cloud_primary,
            model_priority="cloud_first",
        ).invoke({
            "run_id": "cloud-first-fallback-integration",
            "requirement": "make Counter.increment in counter.py advance state on every call",
            "repository_context": {"implementation_required": True},
        })

    assert result["final_status"] == "APPROVED", {
        "route": result["route_history"],
        "errors": [error.detail for error in result["errors"]],
    }
    # Cloud was actually the primary for every role (Product/Architecture/Security/
    # Testing/Reviewer never touch Ollama), and local was used only as the bounded
    # Developer remediation fallback.
    assert len(cloud_primary.attempts) >= 5
    assert any(
        item.provider == "ollama" and item.fallback_used for item in result["model_usage"]
    )
    assert any(
        error.code is ErrorCode.NON_ACTIONABLE_REMEDIATION for error in result["errors"]
    )
    # No stale unchanged Reviewer loop: each Developer visit produced either a
    # concrete pre-gate rejection or forward progress, never an identical no-op replay.
    developer_visits = [i for i, name in enumerate(result["route_history"]) if name == "Developer"]
    assert len(developer_visits) <= 3
    assert len(developer_prompts) == 2
    assert "def __init__(self):" in source.read_text(encoding="utf-8")


class NonActionableEverywhere:
    """Never proposes a mutation and never returns a structured blocker, for either role."""

    def __init__(self, provider: str):
        self.attempts = []
        self.provider = provider

    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
        info = ModelExecutionInfo(
            agent=role, provider=self.provider, requested_model="test",
            actual_model="test", model_profile="TEST",
            fallback_used=mode == "fallback", fallback_reason=fallback_reason,
            latency_ms=1, structured_output_success=True,
        )
        self.attempts.append(info)
        if role is AgentRole.DEVELOPER:
            return candidate.model_copy(update={"mutations": [], "blocker": None}), info
        return candidate, info


def test_cloud_and_local_both_non_actionable_ends_human_review_without_stale_loop(tmp_path):
    """Both providers fail to produce an applicable Developer mutation: the run must
    stop deterministically at HUMAN_REVIEW_REQUIRED, never replay Reviewer with an
    unchanged candidate, and never burn all three MAX_ITERATIONS cycles doing so."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def change_email(current_password, new_email):\n    return new_email\n",
        encoding="utf-8",
    )
    cloud_primary = NonActionableEverywhere("google")
    local_fallback = NonActionableEverywhere("ollama")
    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository,
            model_runtime=local_fallback,
            cloud_runtime=cloud_primary,
            model_priority="cloud_first",
        ).invoke({
            "run_id": "cloud-and-local-exhausted",
            "requirement": "change email after confirming current password",
            "repository_context": {"implementation_required": True},
        })

    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert any(
        error.code is ErrorCode.DEVELOPER_REMEDIATION_EXHAUSTED for error in result["errors"]
    )
    developer_visits = [i for i, name in enumerate(result["route_history"]) if name == "Developer"]
    # Exactly one remediation cycle reached the exhaustion terminal — the graph never
    # replayed Reviewer with the same unchanged candidate for a second or third time.
    assert len(developer_visits) == 2
    assert result["route_history"][-1] == "HUMAN_REVIEW_REQUIRED"
    reviewer_visits = result["route_history"].count("Reviewer")
    assert reviewer_visits <= 1
    # All three chain levels were genuinely attempted for the remediation cycle:
    # cloud primary, cloud secondary (same runtime object, start_index=1), then local.
    developer_cloud_attempts = [a for a in cloud_primary.attempts if a.agent is AgentRole.DEVELOPER]
    developer_local_attempts = [a for a in local_fallback.attempts if a.agent is AgentRole.DEVELOPER]
    assert len(developer_cloud_attempts) == 3
    assert len(developer_local_attempts) == 1


class ChainedCloudDeveloper:
    """A cloud runtime whose Developer behavior depends on the chain position
    (`start_index`): non-actionable at the primary slot (0), and either an
    actionable mutation or another non-actionable response at the secondary
    slot (1) — used to prove the full primary -> secondary -> local chain for
    Developer non-actionable remediation."""

    def __init__(self, secondary_actionable: bool, path: str, content: str):
        self.attempts = []
        self._secondary_actionable = secondary_actionable
        self._path = path
        self._content = content
        self._testing_calls = 0

    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
        provider = "google" if start_index == 0 else "groq"
        info = ModelExecutionInfo(
            agent=role, provider=provider, requested_model="test", actual_model="test",
            model_profile="CLOUD_PRIMARY" if start_index == 0 else "CLOUD_SECONDARY",
            fallback_used=mode == "fallback", fallback_reason=fallback_reason,
            latency_ms=1, structured_output_success=True,
        )
        self.attempts.append(info)
        if role is AgentRole.TESTING:
            self._testing_calls += 1
            mutation = FileMutation(
                path="tests/test_change_email.py",
                operation="create" if self._testing_calls == 1 else "update",
                content=(
                    "from app.service import change_email\n\n\n"
                    "def test_change_email_returns_new_email():\n"
                    "    assert change_email('pw', 'a@b.com') == 'a@b.com'\n"
                ),
            )
            artifact = candidate.model_copy(update={
                "test_mutations": [mutation], "generated_tests": [mutation.path],
            })
            return artifact, info
        if role is not AgentRole.DEVELOPER:
            return candidate, info
        if start_index == 0 or not self._secondary_actionable:
            return candidate.model_copy(update={"mutations": [], "blocker": None}), info
        mutation = FileMutation(path=self._path, operation="update", content=self._content)
        return candidate.model_copy(update={"mutations": [mutation]}), info


def _unreachable_local_runtime():
    class UnreachableLocalRuntime:
        def __init__(self):
            self.attempts = []

        def invoke_artifact(self, *args, **kwargs):
            raise AssertionError("local runtime must not be called while cloud secondary is still viable")

    return UnreachableLocalRuntime()


def test_developer_secondary_cloud_mutation_applies_without_ever_calling_local(tmp_path):
    """L: cloud1 no-op -> cloud2 valid mutation -> Repository MCP -> no local call."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def change_email(current_password, new_email):\n    return new_email\n",
        encoding="utf-8",
    )
    content = "def change_email(current_password, new_email):\n    return new_email.strip()\n"
    cloud = ChainedCloudDeveloper(True, "app/service.py", content)
    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository,
            quality_mcp=PassingQuality(),
            model_runtime=_unreachable_local_runtime(),
            cloud_runtime=cloud,
            model_priority="cloud_first",
        ).invoke({
            "run_id": "cloud-secondary-actionable",
            "requirement": "change email after confirming current password",
            "repository_context": {"implementation_required": True},
        })

    developer_cloud_attempts = [a for a in cloud.attempts if a.agent is AgentRole.DEVELOPER]
    assert len(developer_cloud_attempts) == 3
    assert result["final_status"] == "APPROVED"
    writes = [
        item for item in result["tool_results"]
        if item.tool_name == "update_file" and item.status is ToolStatus.SUCCESS
    ]
    assert writes


def test_developer_both_cloud_non_actionable_falls_back_to_local_mutation(tmp_path):
    """M: cloud1 no-op -> cloud2 no-op -> local valid mutation -> Repository MCP."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "service.py").write_text(
        "def change_email(current_password, new_email):\n    return new_email\n",
        encoding="utf-8",
    )
    content = "def change_email(current_password, new_email):\n    return new_email.strip()\n"

    class ActionableLocalRuntime:
        def __init__(self):
            self.attempts = []

        def invoke_artifact(self, role, envelope, candidate, *, mode="fallback", fallback_reason=None, start_index=0):
            info = ModelExecutionInfo(
                agent=role, provider="ollama", requested_model="qwen3.5:9b", actual_model="qwen3.5:9b",
                model_profile="LOCAL", fallback_used=True, fallback_reason=fallback_reason,
                latency_ms=1, structured_output_success=True,
            )
            self.attempts.append(info)
            if role is not AgentRole.DEVELOPER:
                return candidate, info
            mutation = FileMutation(path="app/service.py", operation="update", content=content)
            return candidate.model_copy(update={"mutations": [mutation]}), info

    cloud = ChainedCloudDeveloper(False, "app/service.py", content)
    local = ActionableLocalRuntime()
    with MCPRepositoryClient(tmp_path) as repository:
        result = build_engineering_graph(
            repository_mcp=repository,
            quality_mcp=PassingQuality(),
            model_runtime=local,
            cloud_runtime=cloud,
            model_priority="cloud_first",
        ).invoke({
            "run_id": "cloud-exhausted-local-actionable",
            "requirement": "change email after confirming current password",
            "repository_context": {"implementation_required": True},
        })

    developer_cloud_attempts = [a for a in cloud.attempts if a.agent is AgentRole.DEVELOPER]
    developer_local_attempts = [a for a in local.attempts if a.agent is AgentRole.DEVELOPER]
    assert len(developer_cloud_attempts) == 3
    assert len(developer_local_attempts) == 1
    assert result["final_status"] == "APPROVED"
    writes = [
        item for item in result["tool_results"]
        if item.tool_name == "update_file" and item.status is ToolStatus.SUCCESS
    ]
    assert writes


class FailingLocalRuntime:
    def __init__(self):
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
        info = ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local", actual_model=None,
            model_profile="LOCAL", degraded=True, latency_ms=1,
            structured_output_success=False, error="LLM_AVAILABILITY_ERROR: unavailable",
        )
        self.attempts.append(info)
        raise RuntimeError(info.error)


class TimingOutLocalRuntime(FailingLocalRuntime):
    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
        info = ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local", actual_model=None,
            model_profile="LOCAL", degraded=True, latency_ms=1,
            structured_output_success=False, error="AGENT_TIMEOUT: controlled",
        )
        self.attempts.append(info)
        raise RuntimeError(info.error)


class ExhaustedQualityRuntime:
    def __init__(self):
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None, start_index=0):
        if role is AgentRole.TESTING:
            info = ModelExecutionInfo(
                agent=role, provider="ollama", requested_model="local",
                actual_model="local", model_profile="LOCAL", degraded=True,
                latency_ms=1, structured_output_success=False,
                error="LLM_QUALITY_ERROR: invalid structured response",
            )
            self.attempts.append(info)
            raise RuntimeError(info.error)
        info = ModelExecutionInfo(
            agent=role, provider="ollama", requested_model="local",
            actual_model="local", model_profile="LOCAL", latency_ms=1,
            structured_output_success=True,
        )
        self.attempts.append(info)
        return candidate, info


def test_exhausted_testing_quality_error_routes_to_explicit_human_review() -> None:
    result = build_engineering_graph(
        model_runtime=ExhaustedQualityRuntime(),
    ).invoke({"run_id": "testing-quality-terminal", "requirement": "document behavior"})

    assert result["final_status"] == "HUMAN_REVIEW_REQUIRED"
    assert result["route_history"][-1] == "HUMAN_REVIEW_REQUIRED"
    assert result["human_review_required"] is True
    assert any(
        error.code is ErrorCode.LLM_QUALITY_ERROR
        and error.source_stage == AgentRole.TESTING.value
        for error in result["errors"]
    )


class SuccessfulCloudRuntime:
    def __init__(self):
        self.attempts = []

    def invoke_artifact(self, role, envelope, candidate, *, mode="fallback", fallback_reason=None, start_index=0):
        return candidate, ModelExecutionInfo(
            agent=role, provider="google", requested_model="gemini-3.7-flash",
            actual_model="gemini-3.7-flash", model_profile="CLOUD_FALLBACK",
            fallback_used=True, fallback_reason=fallback_reason, latency_ms=2,
            structured_output_success=True,
        )


def test_local_failure_uses_graph_integrated_cloud_fallback_and_preserves_error():
    result = build_engineering_graph(
        model_runtime=FailingLocalRuntime(), cloud_runtime=SuccessfulCloudRuntime(),
        model_priority="local_first",
    ).invoke({"run_id": "fallback", "requirement": "safe bounded change"})

    assert result["final_status"] == "APPROVED"
    assert result["errors"][0].code.value == "LLM_AVAILABILITY_ERROR"
    assert any(item.fallback_used for item in result["model_usage"])
    assert result["model_usage"][1].fallback_reason == "LLM_AVAILABILITY_ERROR"


def test_local_failure_without_cloud_routes_to_terminal_hitl_instead_of_crashing():
    result = build_engineering_graph(model_runtime=FailingLocalRuntime()).invoke(
        {"run_id": "no-cloud", "requirement": "safe bounded change"}
    )

    assert result["final_status"] == "INCOMPLETE"
    assert result["route_history"] == ["Product", "INCOMPLETE"]


def test_agent_timeout_is_preserved_in_workflow_and_langfuse():
    trace = LangfuseTracer().start_run("agent-timeout", "safe bounded change")
    result = build_engineering_graph(
        model_runtime=TimingOutLocalRuntime(), trace=trace
    ).invoke({"run_id": "agent-timeout", "requirement": "safe bounded change"})

    assert result["final_status"] == "INCOMPLETE"
    assert result["errors"][0].code is ErrorCode.AGENT_TIMEOUT
    assert result["model_usage"][0].error.startswith("AGENT_TIMEOUT")
    assert any(event["name"] == "AGENT_TIMEOUT" for event in trace.events)


def test_failed_cloud_attempt_preserves_budget_model_attempt_and_completed_evidence():
    cloud = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key="configured"),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"error": "rate limited"})
        )),
    )
    result = build_engineering_graph(
        model_runtime=FailingLocalRuntime(), cloud_runtime=cloud,
        model_priority="local_first",
    ).invoke({"run_id": "cloud-fail", "requirement": "safe bounded change"})

    assert result["final_status"] == "INCOMPLETE"
    assert result["cloud_escalations_run"] == 1
    assert result["cloud_escalations_by_agent"] == {"Product": 1}
    assert result["model_usage"][-1].provider == "google"
    assert result["model_usage"][-1].error.startswith("CLOUD_FALLBACK_UNAVAILABLE")
    assert "rag_evidence" in result and "tool_results" in result
