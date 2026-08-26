import json

import httpx
import pytest

from engineering_team.config import Settings
from engineering_team.contracts.enums import (
    ActionMode,
    AgentRole,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import (
    ArchitectureProposal,
    FileMutation,
    ImplementationResult,
    ProductSpecification,
    RetrievedEvidence,
    ReviewerDecision,
    SecurityFinding,
    SecurityReview,
    ToolResult,
)
from engineering_team.contracts.models import TestResult as EngineeringTestResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.runtime import (
    LocalModelRuntime,
    _preserves_governed_facts,
)
from engineering_team.llm.runtime import TestingMutationPlan as MutationPlan
from engineering_team.models.context import build_context
from engineering_team.observability.langfuse import LangfuseTracer


def test_runtime_routes_model_and_validates_actual_structured_response() -> None:
    requests = []
    candidate = ArchitectureProposal(
        components=["API"], apis=["POST /reset"], data_changes=[], integrations=[],
        dependencies=[], decisions=["single use"], risks=[], impact="bounded",
    )

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "qwen3.5:4b",
                "response": candidate.model_dump_json(),
                "prompt_eval_count": 10,
                "eval_count": 8,
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    trace = LangfuseTracer().start_run("runtime", "requirement")
    runtime = LocalModelRuntime(Settings(_env_file=None), client=client, trace=trace)
    envelope = build_context(
        AgentRole.ARCHITECTURE,
        EngineeringState(run_id="runtime", requirement="bounded API"),
        "Architecture",
    )

    artifact, info = runtime.invoke_artifact(AgentRole.ARCHITECTURE, envelope, candidate)

    assert info.requested_model == "qwen3.5:4b"
    assert info.actual_model == "qwen3.5:4b"
    assert info.structured_output_success is True
    assert info.fallback_used is False
    assert artifact == candidate
    assert runtime.outputs[AgentRole.ARCHITECTURE] == candidate
    assert requests[0]["format"]["type"] == "object"
    assert set(requests[0]["format"]["required"]) == set(
        requests[0]["format"]["properties"]
    )
    assert requests[0]["system"] != requests[0]["prompt"]
    assert requests[0]["prompt"].rfind("Candidate artifact:") > requests[0]["prompt"].rfind(
        "Output schema:"
    )
    assert "FIELD POLICY:" in requests[0]["prompt"]
    assert "additive fields may add grounded items" in requests[0]["prompt"]
    assert "Copy every candidate key and value exactly" not in requests[0]["prompt"]
    assert any(event["name"] == "Architecture model" for event in trace.events)


def test_runtime_rejects_schema_valid_contradiction_after_one_repair() -> None:
    candidate = ArchitectureProposal(
        components=["API"], apis=[], data_changes=[], integrations=[], dependencies=[],
        decisions=[], risks=["must preserve"], impact="safe",
    )
    altered = candidate.model_copy(update={"risks": []})
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200, json={"model": "qwen3.5:4b", "response": altered.model_dump_json()}
    )))
    runtime = LocalModelRuntime(Settings(_env_file=None), client=client)
    envelope = build_context(
        AgentRole.ARCHITECTURE,
        EngineeringState(run_id="runtime", requirement="bounded API"), "Architecture",
    )

    import pytest
    with pytest.raises(RuntimeError, match="governed artifact contradiction"):
        runtime.invoke_artifact(AgentRole.ARCHITECTURE, envelope, candidate)
    assert len(runtime.attempts) == 2


def test_governed_repair_replaces_verbose_prompt_with_exact_candidate() -> None:
    candidate = ReviewerDecision(
        status=ReviewerStatus.REJECTED,
        score=40,
        subscores={"security_compliance": 0},
        reason="security findings require code remediation",
        problems=["authorization finding"],
        remediation_category=RemediationCategory.SECURITY,
        return_to=RouteTarget.DEVELOPER,
        confidence=1,
        evidence_references=["mcp://quality/run_security_scan"],
    )
    incomplete = candidate.model_copy(update={
        "problems": [], "remediation_category": None, "return_to": None,
    })
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        response = incomplete if len(requests) == 1 else candidate
        return httpx.Response(
            200, json={"model": "qwen3.5:9b", "response": response.model_dump_json()}
        )

    runtime = LocalModelRuntime(
        Settings(_env_file=None), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    envelope = build_context(
        AgentRole.REVIEWER,
        EngineeringState(run_id="runtime", requirement="reject unsafe access"),
        "Reviewer",
    )

    artifact, _ = runtime.invoke_artifact(AgentRole.REVIEWER, envelope, candidate)

    assert artifact == candidate
    assert len(requests) == 2
    assert requests[1]["prompt"].startswith("Repair governed artifact contradiction")
    assert "Output schema:" not in requests[1]["prompt"]
    assert json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False) in requests[1]["prompt"]


def test_semantic_guard_rejects_invented_source_and_material_developer_change() -> None:
    architecture = ArchitectureProposal(
        components=["API"], apis=[], data_changes=[], integrations=[], dependencies=[],
        decisions=[], risks=[], impact="safe", evidence_references=["retrieved:1"],
    )
    invented = architecture.model_copy(
        update={"evidence_references": ["retrieved:1", "invented:99"]}
    )
    implementation = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=["app.py"],
        diff="PROPOSED TECHNICAL CHANGE\n--- app.py\n+++ app.py\n+ bounded change",
        evidence=["mcp://repository/list_files"],
        validation_result="PROPOSED validation: run tests", security_surface_changed=False,
    )
    fabricated = implementation.model_copy(update={
        "action_mode": ActionMode.APPLIED, "changed_files": ["invented.py"],
        "diff": "+ unsafe", "validation_result": "passed",
    })

    assert not _preserves_governed_facts(architecture.model_dump(mode="json"), invented)
    assert not _preserves_governed_facts(implementation.model_dump(mode="json"), fabricated)


def test_developer_prompt_requires_bounded_mutations_for_a_viable_change() -> None:
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=["app/email.py"],
        diff="PROPOSED\n+ change", evidence=["mcp://repository/read_file#app/email.py"],
        validation_result="run tests", security_surface_changed=False,
    )
    runtime = LocalModelRuntime(Settings(_env_file=None))
    envelope = build_context(
        AgentRole.DEVELOPER,
        EngineeringState(run_id="runtime", requirement="change email"),
        "change email",
    )

    _, prompt = runtime._prompts(AgentRole.DEVELOPER, envelope, type(candidate), candidate.model_dump(mode="json"))

    assert "When inspected evidence supports a viable change, return one or more mutations" in prompt
    assert "Copy every candidate key and value exactly" not in prompt


def test_developer_prompt_keeps_complete_editable_source_context() -> None:
    source = ("value = 1\n" * 250) + "TAIL_SENTINEL = 'password-change-boundary'\n"
    inspected = ToolResult(
        tool_name="read_file",
        allowed_role=AgentRole.DEVELOPER,
        status=ToolStatus.SUCCESS,
        input_summary="path=app/service.py",
        output_summary=source,
        duration_ms=1,
        evidence_reference="mcp://repository/read_file",
    )
    state = EngineeringState(
        run_id="runtime",
        requirement="add password change",
        tool_results=[inspected],
    )
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED,
        changed_files=["app/service.py"],
        diff="PROPOSED\n+change",
        evidence=["mcp://repository/read_file#app/service.py"],
        validation_result="run tests",
    )
    runtime = LocalModelRuntime(Settings(_env_file=None))
    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)

    _, prompt = runtime._prompts(
        AgentRole.DEVELOPER,
        envelope,
        type(candidate),
        candidate.model_dump(mode="json"),
    )

    assert len(source) > 1_200
    assert len(source) <= 4_000
    assert "TAIL_SENTINEL = 'password-change-boundary'" in prompt


def test_architecture_developer_and_testing_prompts_include_governed_requirement_facts() -> None:
    specification = ProductSpecification(
        objective="change a password safely",
        actors=["account owner"],
        business_rules=["The current password must match before any update."],
        constraints=["Do not store plaintext credentials."],
        acceptance_criteria=["A wrong current password is rejected without changing state."],
        nfrs=["secure"],
        ambiguities=[],
        assumptions=[],
        source_requirement="allow password changes after confirming the current password",
    )
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["app/service.py"],
        diff="--- a/app/service.py\n+++ b/app/service.py\n+def change_password():\n+    pass\n",
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    state = EngineeringState(
        run_id="facts",
        requirement=specification.source_requirement,
        specification=specification,
        implementation=implementation,
    )
    runtime = LocalModelRuntime(Settings(_env_file=None))

    architecture_candidate = ArchitectureProposal(
        components=["modular monolith"],
        apis=[],
        data_changes=[],
        integrations=[],
        dependencies=[],
        decisions=["preserve modular boundaries"],
        risks=[],
        impact="bounded",
    )
    _, architecture_prompt = runtime._prompts(
        AgentRole.ARCHITECTURE,
        build_context(AgentRole.ARCHITECTURE, state, state.requirement),
        type(architecture_candidate),
        architecture_candidate.model_dump(mode="json"),
    )

    _, developer_prompt = runtime._prompts(
        AgentRole.DEVELOPER,
        build_context(AgentRole.DEVELOPER, state, state.requirement),
        type(implementation),
        implementation.model_dump(mode="json"),
    )
    from engineering_team.agents.testing import TestingAgent

    testing_candidate = TestingAgent().execute(
        build_context(AgentRole.TESTING, state, state.requirement)
    )
    _, testing_prompt = runtime._prompts(
        AgentRole.TESTING,
        build_context(AgentRole.TESTING, state, state.requirement),
        type(testing_candidate),
        testing_candidate.model_dump(mode="json"),
    )

    for prompt in (architecture_prompt, developer_prompt, testing_prompt):
        assert "The current password must match before any update." in prompt
        assert "A wrong current password is rejected without changing state." in prompt
    assert "change_password" in testing_prompt


def test_testing_mutation_plan_rejects_duplicate_normalized_paths() -> None:
    mutation = FileMutation(
        path="tests/test_service.py",
        operation="update",
        content="def test_change_password():\n    assert True\n",
    )

    with pytest.raises(ValueError, match="unique normalized paths"):
        MutationPlan(test_mutations=[
            mutation,
            mutation.model_copy(update={"path": "tests\\test_service.py"}),
        ])


def test_testing_mutation_plan_accepts_at_most_one_test_file() -> None:
    first = FileMutation(
        path="tests/test_counter.py",
        operation="create",
        content="def test_counter():\n    assert True\n",
    )
    second = FileMutation(
        path="tests/test_counter_edge.py",
        operation="create",
        content="def test_counter_edge():\n    assert True\n",
    )

    with pytest.raises(ValueError, match="at most 1 item"):
        MutationPlan(test_mutations=[first, second])


def test_developer_runtime_prioritizes_candidate_paths_over_latest_reads() -> None:
    reads = [
        ToolResult(
            tool_name="read_file", allowed_role=AgentRole.DEVELOPER,
            status=ToolStatus.SUCCESS, input_summary=f"path={path}",
            output_summary=content, duration_ms=1,
            evidence_reference="mcp://repository/read_file",
        )
        for path, content in (
            ("app/service.py", "SERVICE_SENTINEL = True\n"),
            ("app/main.py", "MAIN_SENTINEL = True\n"),
            ("app/__init__.py", "PACKAGE_SENTINEL = True\n"),
        )
    ]
    state = EngineeringState(
        run_id="preferred-context", requirement="change service behavior", tool_results=reads,
    )
    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=["app/service.py"],
        diff="PROPOSED\n+change", evidence=["mcp://repository/read_file#app/service.py"],
        validation_result="run tests",
    )
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "qwen3.5:9b",
            "response": json.dumps({"mutations": [], "no_mutation_reason": "not enough context"}),
        })

    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate)

    assert "app/service.py" in requests[0]["prompt"]
    assert "SERVICE_SENTINEL" in requests[0]["prompt"]
    assert "PACKAGE_SENTINEL" not in requests[0]["prompt"]


def test_developer_prompt_contains_prior_diff_and_bounded_causal_test_failure() -> None:
    causal = "AssertionError: increment returned 0 instead of 1"
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["src/counter.py"],
        diff="--- a/src/counter.py\n+++ b/src/counter.py\n+def increment(): return 0\n",
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    failed_tool = ToolResult(
        tool_name="run_tests",
        allowed_role=AgentRole.TESTING,
        status=ToolStatus.FAIL,
        input_summary="safe",
        output_summary=causal,
        duration_ms=1,
        evidence_reference="mcp://quality/run_tests",
    )
    state = EngineeringState(
        run_id="causal-prompt",
        requirement="increment a stored counter",
        implementation=implementation,
        test_results=[EngineeringTestResult(
            proposed_tests=["increment"], generated_tests=["tests/test_counter.py"],
            executed_tests=["run_tests"], actual_results=[causal],
            status=ToolStatus.FAIL, failures=[causal], coverage_mapping={},
            evidence_references=["mcp://quality/run_tests"],
        )],
        tool_results=[failed_tool],
        remediation_request="workspace test validation unsuccessful",
        iteration=1,
    )
    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)
    candidate = implementation.model_copy(update={"action_mode": ActionMode.PROPOSED})

    _, prompt = LocalModelRuntime(Settings(_env_file=None))._prompts(
        AgentRole.DEVELOPER,
        envelope,
        type(candidate),
        candidate.model_dump(mode="json"),
    )

    assert '"remediation_context"' in prompt
    assert causal in prompt
    assert "mcp://quality/run_tests" in prompt
    assert "+def increment(): return 0" in prompt


def test_quality_repair_is_self_contained_and_traced_as_recoverable() -> None:
    invalid_response = '{"mutations":[{"path":"app/service.py","operation":"update"'
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        response = (
            invalid_response
            if len(requests) == 1
            else json.dumps({"mutations": [], "no_mutation_reason": "not viable"})
        )
        return httpx.Response(200, json={"model": "qwen3.5:9b", "response": response})

    trace = LangfuseTracer().start_run("quality-repair", "change password")
    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        trace=trace,
    )
    state = EngineeringState(run_id="quality-repair", requirement="change password")
    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED,
        changed_files=["app/service.py"],
        diff="PROPOSED\n+change",
        evidence=["mcp://repository/read_file#app/service.py"],
        validation_result="run tests",
    )

    runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate)

    assert len(requests) == 2
    assert invalid_response in requests[1]["prompt"]
    model_events = [event for event in trace.events if event["name"] == "Developer model"]
    assert model_events[0]["level"] == "WARNING"
    assert model_events[0]["metadata"]["structured_output_success"] is False
    assert model_events[1]["level"] == "DEFAULT"


def test_exhausted_quality_repair_is_traced_as_error() -> None:
    trace = LangfuseTracer().start_run("quality-exhausted", "change password")
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        200,
        json={"model": "qwen3.5:9b", "response": '{"mutations":['},
    )))
    runtime = LocalModelRuntime(Settings(_env_file=None), client=client, trace=trace)
    state = EngineeringState(run_id="quality-exhausted", requirement="change password")
    envelope = build_context(AgentRole.DEVELOPER, state, state.requirement)
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED,
        changed_files=["app/service.py"],
        diff="PROPOSED\n+change",
        evidence=["mcp://repository/read_file#app/service.py"],
        validation_result="run tests",
    )

    with pytest.raises(RuntimeError, match="invalid structured response"):
        runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate)

    model_events = [event for event in trace.events if event["name"] == "Developer model"]
    assert [event["level"] for event in model_events] == ["WARNING", "ERROR"]


def test_testing_invalid_json_gets_one_small_schema_only_repair_prompt() -> None:
    invalid = '{"test_mutations":[' + ("x" * 10_000) + "TAIL_CAUSE"
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        response = (
            invalid
            if len(requests) == 1
            else json.dumps({
                "test_mutations": [],
                "no_mutation_reason": "repository evidence is insufficient",
            })
        )
        return httpx.Response(200, json={"model": "qwen3.5:9b", "response": response})

    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    state = EngineeringState(run_id="testing-repair", requirement="verify behavior")
    candidate = EngineeringTestResult(
        proposed_tests=["exercise behavior"], generated_tests=[], executed_tests=[],
        actual_results=[], status=ToolStatus.SUCCESS, failures=[],
        coverage_mapping={}, evidence_references=[],
    )

    runtime.invoke_artifact(
        AgentRole.TESTING,
        build_context(AgentRole.TESTING, state, state.requirement),
        candidate,
    )

    assert len(requests) == 2
    assert len(requests[1]["prompt"]) < 6_000
    assert "Output schema:" in requests[1]["prompt"]
    assert "TAIL_CAUSE" in requests[1]["prompt"]
    assert "ContextEnvelope:" not in requests[1]["prompt"]


def test_developer_runtime_uses_a_small_mutation_plan_schema() -> None:
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=["app/service.py"],
        diff="PROPOSED\n+change", evidence=["mcp://repository/read_file#app/service.py"],
        validation_result="run tests",
    )
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "qwen3.5:9b",
            "response": json.dumps({"mutations": [], "no_mutation_reason": "not enough context"}),
        })

    runtime = LocalModelRuntime(
        Settings(_env_file=None), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    envelope = build_context(
        AgentRole.DEVELOPER,
        EngineeringState(run_id="runtime", requirement="change email"),
        "change email",
    )

    output, _ = runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate)

    assert output.action_mode is ActionMode.PROPOSED
    assert set(requests[0]["format"]["properties"]) == {
        "mutations", "no_mutation_reason", "blocker",
    }
    assert "PROPOSED TECHNICAL CHANGE" not in requests[0]["prompt"]
    assert requests[0]["options"]["num_predict"] >= 4_096


def test_reviewer_output_budget_can_hold_the_complete_decision_schema() -> None:
    assert LocalModelRuntime._output_limit(AgentRole.REVIEWER) >= 1_200


@pytest.mark.parametrize(
    ("manifest_name", "manifest_content", "test_path"),
    [
        ("pyproject.toml", "[project]\nname = 'sample'\n", "tests/test_email_change.py"),
        (
            "package.json",
            '{"scripts":{"test":"vitest run"}}\n',
            "tests/nova/email.test.ts",
        ),
    ],
)
def test_testing_runtime_accepts_only_a_small_native_test_mutation_plan(
    tmp_path, manifest_name, manifest_content, test_path
) -> None:
    from engineering_team.capabilities import detect_project_capabilities

    (tmp_path / manifest_name).write_text(manifest_content, encoding="utf-8")
    profile = detect_project_capabilities(tmp_path)
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED, changed_files=["app/email.py"],
        diff="--- a/app/email.py\n+++ b/app/email.py\n+def change_email(current_password, email):\n",
        evidence=["mcp://repository/get_diff"], validation_result="applied",
    )
    state = EngineeringState(
        run_id="runtime", requirement="change email after confirming the current password",
        implementation=implementation, project_capabilities=profile,
    )
    from engineering_team.agents.testing import TestingAgent

    envelope = build_context(AgentRole.TESTING, state, state.requirement)
    candidate = TestingAgent().execute(envelope)
    requests: list[dict] = []

    def handler(request):
        requests.append(json.loads(request.content))
        response = {
            "test_mutations": [{
                "path": test_path,
                "operation": "create",
                "content": "complete native behavioral test\n",
            }],
            "no_mutation_reason": None,
        }
        return httpx.Response(
            200, json={"model": "qwen3.5:4b", "response": json.dumps(response)}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    runtime = LocalModelRuntime(Settings(_env_file=None), client=client)

    output, _ = runtime.invoke_artifact(AgentRole.TESTING, envelope, candidate)

    assert output.test_mutations[0].path == test_path
    assert output.generated_tests == [test_path]
    assert set(requests[0]["format"]["properties"]) == {
        "test_mutations", "no_mutation_reason",
    }
    assert requests[0]["format"]["properties"]["test_mutations"]["maxItems"] == 1
    assert requests[0]["options"]["num_predict"] <= 3_072
    assert "executed_tests" not in requests[0]["prompt"].split("Candidate artifact:", 1)[1]


def test_testing_prompt_requires_behavioral_setup_from_repository_evidence() -> None:
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED,
        changed_files=["src/counter.py"],
        diff=(
            "--- a/src/counter.py\n+++ b/src/counter.py\n"
            "+class Counter:\n+    def increment(self): return 1\n"
        ),
        evidence=["mcp://repository/get_diff"],
        validation_result="applied",
    )
    state = EngineeringState(
        run_id="behavioral-setup",
        requirement="increment a stored counter",
        implementation=implementation,
    )
    from engineering_team.agents.testing import TestingAgent

    envelope = build_context(AgentRole.TESTING, state, state.requirement)
    candidate = TestingAgent().execute(envelope)

    _, prompt = LocalModelRuntime(Settings(_env_file=None))._prompts(
        AgentRole.TESTING,
        envelope,
        type(candidate),
        candidate.model_dump(mode="json"),
    )

    assert "existing public/domain setup API" in prompt
    assert "existing repository fixture/helper" in prompt
    assert "actual implementation contract" in prompt
    assert "Do not invent opaque setup values" in prompt
    assert "exercise behavior" in prompt


def test_mocked_security_model_may_strengthen_scanner_pass_to_grounded_fail() -> None:
    baseline = SecurityReview(
        status=SecurityStatus.PASS,
        highest_severity=SecuritySeverity.INFO,
        findings=[], recommendations=[], sources=["scanner://baseline"],
        checklist={key: "PASS" for key in (
            "authentication", "authorization", "input_validation", "sensitive_information",
            "secrets", "injection", "access_control", "idor", "logging", "data_protection",
            "api_abuse", "rate_limiting", "owasp",
        )},
    )
    finding = SecurityFinding(
        category="input_validation", severity=SecuritySeverity.HIGH,
        description="unvalidated input reaches a sensitive operation",
        affected_evidence=["rag://owasp/input-validation"],
        recommendation="validate the input",
    )
    strengthened = baseline.model_copy(update={
        "status": SecurityStatus.FAIL,
        "highest_severity": SecuritySeverity.HIGH,
        "findings": [finding],
        "recommendations": ["validate the input"],
        "sources": ["scanner://baseline", "rag://owasp/input-validation"],
        "checklist": {**baseline.checklist, "input_validation": "FAIL"},
        "requires_hitl": True,
    })
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
        200, json={"model": "qwen3.5:9b", "response": strengthened.model_dump_json()}
    )))
    runtime = LocalModelRuntime(Settings(_env_file=None), client=client)
    state = EngineeringState(run_id="security-strengthen", requirement="validate input")

    artifact, _ = runtime.invoke_artifact(
        AgentRole.SECURITY,
        build_context(AgentRole.SECURITY, state, state.requirement),
        baseline,
    )

    assert artifact.status is SecurityStatus.FAIL
    assert artifact.findings == [finding]
    assert len(runtime.attempts) == 1


def test_mocked_security_model_cannot_weaken_deterministic_fail_to_pass() -> None:
    checklist = {key: "PASS" for key in (
        "authentication", "authorization", "input_validation", "sensitive_information",
        "secrets", "injection", "access_control", "idor", "logging", "data_protection",
        "api_abuse", "rate_limiting", "owasp",
    )}
    finding = SecurityFinding(
        category="authorization", severity=SecuritySeverity.HIGH,
        description="authorization is missing", affected_evidence=["scanner://finding"],
        recommendation="enforce authorization",
    )
    baseline = SecurityReview(
        status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.HIGH,
        findings=[finding], recommendations=["enforce authorization"],
        sources=["scanner://finding"],
        checklist={**checklist, "authorization": "FAIL"}, requires_hitl=True,
    )
    weakened = baseline.model_copy(update={
        "status": SecurityStatus.PASS, "highest_severity": SecuritySeverity.INFO,
        "checklist": checklist, "requires_hitl": False,
    })
    runtime = LocalModelRuntime(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(
            200, json={"model": "qwen3.5:9b", "response": weakened.model_dump_json()}
        ))),
    )
    state = EngineeringState(run_id="security-weaken", requirement="enforce access")

    with pytest.raises(RuntimeError, match="governed artifact contradiction"):
        runtime.invoke_artifact(
            AgentRole.SECURITY,
            build_context(AgentRole.SECURITY, state, state.requirement),
            baseline,
        )

    assert len(runtime.attempts) == 2


def test_security_prompt_receives_governed_artifacts_diff_and_scanner_evidence() -> None:
    specification = ProductSpecification(
        objective="validate an operation", actors=["caller"], business_rules=["reject invalid input"],
        constraints=["preserve behavior"], acceptance_criteria=["valid input succeeds"],
        nfrs=["secure"], ambiguities=[], assumptions=[], source_requirement="validate operation",
    )
    architecture = ArchitectureProposal(
        components=["operation service"], apis=["public operation"], data_changes=[],
        integrations=[], dependencies=[], decisions=["validate at boundary"], risks=["bad input"],
        impact="bounded",
    )
    implementation = ImplementationResult(
        action_mode=ActionMode.APPLIED, changed_files=["src/operation.py"],
        diff="+def operate(value): return sink(value)",
        evidence=["mcp://repository/get_diff"], validation_result="applied",
        security_surface_changed=True,
    )
    scanner = ToolResult(
        tool_name="run_security_scan", allowed_role=AgentRole.SECURITY,
        status=ToolStatus.FAIL, input_summary="safe",
        output_summary="scanner found unvalidated flow into sink",
        duration_ms=1, evidence_reference="mcp://quality/run_security_scan",
    )
    state = EngineeringState(
        run_id="security-context", requirement="validate operation",
        specification=specification, architecture=architecture,
        implementation=implementation, tool_results=[scanner],
    )
    candidate = SecurityReview(
        status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.HIGH,
        findings=[], recommendations=[], sources=["mcp://quality/run_security_scan"],
        checklist={key: ("FAIL" if key == "input_validation" else "PASS") for key in (
            "authentication", "authorization", "input_validation", "sensitive_information",
            "secrets", "injection", "access_control", "idor", "logging", "data_protection",
            "api_abuse", "rate_limiting", "owasp",
        )},
    )

    _, prompt = LocalModelRuntime(Settings(_env_file=None))._prompts(
        AgentRole.SECURITY,
        build_context(AgentRole.SECURITY, state, state.requirement),
        type(candidate), candidate.model_dump(mode="json"),
    )

    assert '"product_basis"' in prompt
    assert '"architecture_basis"' in prompt
    assert '"implementation_basis"' in prompt
    assert "+def operate(value): return sink(value)" in prompt
    assert "scanner found unvalidated flow into sink" in prompt
    assert "mcp://quality/run_security_scan" in prompt
    assert "may strengthen PASS to FAIL" in prompt
    assert "Preserve all governed facts, findings, statuses" not in prompt


@pytest.mark.parametrize(
    ("role", "domain"),
    [
        (AgentRole.ARCHITECTURE, "architecture"),
        (AgentRole.SECURITY, "owasp"),
        (AgentRole.TESTING, "testing"),
    ],
)
def test_reasoning_prompts_receive_bounded_rag_fragment_and_provenance(role, domain) -> None:
    fragment = "RAG_FRAGMENT_SENTINEL " + ("grounded guidance " * 200)
    evidence = RetrievedEvidence(
        source="governance.md", section="bounded-context", version="1",
        chunk_id="chunk-42", fragment=fragment, domain=domain,
        query="bounded reasoning", score=0.91,
    )
    state = EngineeringState(
        run_id="rag-fragment", requirement="apply bounded guidance",
        rag_evidence=[evidence],
    )
    if role is AgentRole.ARCHITECTURE:
        candidate = ArchitectureProposal(
            components=["service"], apis=[], data_changes=[], integrations=[],
            dependencies=[], decisions=[], risks=[], impact="bounded",
        )
    elif role is AgentRole.SECURITY:
        candidate = SecurityReview(
            status=SecurityStatus.PASS, highest_severity=SecuritySeverity.INFO,
            findings=[], recommendations=[], sources=[],
            checklist={key: "PASS" for key in (
                "authentication", "authorization", "input_validation", "sensitive_information",
                "secrets", "injection", "access_control", "idor", "logging", "data_protection",
                "api_abuse", "rate_limiting", "owasp",
            )},
        )
    else:
        candidate = EngineeringTestResult(
            proposed_tests=[], generated_tests=[], executed_tests=[], actual_results=[],
            status=ToolStatus.SUCCESS, failures=[], coverage_mapping={}, evidence_references=[],
        )

    _, prompt = LocalModelRuntime(Settings(_env_file=None))._prompts(
        role, build_context(role, state, state.requirement),
        type(candidate), candidate.model_dump(mode="json"),
    )

    assert "RAG_FRAGMENT_SENTINEL" in prompt
    assert '"source": "governance.md"' in prompt
    assert '"section": "bounded-context"' in prompt
    assert '"chunk_id": "chunk-42"' in prompt
    assert '"score": 0.91' in prompt
    assert len(fragment) > 800
    assert ("grounded guidance " * 60) not in prompt


def test_runtime_classifies_configured_http_timeout_as_agent_timeout() -> None:
    state = EngineeringState(run_id="timeout", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    from engineering_team.agents.product import ProductAgent

    candidate = ProductAgent().execute(envelope)

    def timeout(request):
        raise httpx.ReadTimeout("controlled timeout", request=request)

    trace = LangfuseTracer().start_run("timeout", "safe change")
    runtime = LocalModelRuntime(
        Settings(_env_file=None, max_local_retries=1),
        client=httpx.Client(transport=httpx.MockTransport(timeout)),
        trace=trace,
    )

    with pytest.raises(RuntimeError, match="^AGENT_TIMEOUT"):
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate)

    assert len(runtime.attempts) == 2
    assert all(item.error and item.error.startswith("AGENT_TIMEOUT") for item in runtime.attempts)
    assert all(event["status_message"].startswith("AGENT_TIMEOUT") for event in trace.events)


def test_runtime_keeps_connectivity_failure_distinct_from_agent_timeout() -> None:
    state = EngineeringState(run_id="unavailable", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    from engineering_team.agents.product import ProductAgent

    candidate = ProductAgent().execute(envelope)

    def unavailable(request):
        raise httpx.ConnectError("controlled unavailable", request=request)

    runtime = LocalModelRuntime(
        Settings(_env_file=None, max_local_retries=1),
        client=httpx.Client(transport=httpx.MockTransport(unavailable)),
    )

    with pytest.raises(RuntimeError, match="^LLM_AVAILABILITY_ERROR"):
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate)
