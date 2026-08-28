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
)
from engineering_team.contracts.models import (
    ArchitectureProposal,
    ImplementationResult,
    ReviewerDecision,
    ProductSpecification,
)
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.runtime import LocalModelRuntime, _preserves_governed_facts
from engineering_team.models.context import build_context
from engineering_team.observability.langfuse import LangfuseTracer


def test_product_can_replace_generic_placeholder_but_not_real_acceptance_facts():
    candidate = ProductSpecification(objective="recover account", actors=["User"],
        business_rules=[], constraints=[], acceptance_criteria=["Requirement is fulfilled"],
        nfrs=[], ambiguities=[], assumptions=[], source_requirement="recover account")
    detailed = candidate.model_copy(update={"acceptance_criteria": ["Recovery token expires after 15 minutes"]})
    assert _preserves_governed_facts(candidate.model_dump(mode="json"), detailed)
    governed = candidate.model_copy(update={"acceptance_criteria": ["Recovery token expires after 15 minutes"]})
    weakened = governed.model_copy(update={"acceptance_criteria": ["Token exists"]})
    assert not _preserves_governed_facts(governed.model_dump(mode="json"), weakened)
    rewritten = detailed.model_copy(update={"source_requirement": "different request"})
    assert not _preserves_governed_facts(candidate.model_dump(mode="json"), rewritten)


def test_applied_python_must_parse_without_silently_unescaping_source():
    candidate = ImplementationResult(action_mode=ActionMode.APPLIED, changed_files=["app.py"],
        diff="pending", evidence=["read:app.py"], validation_result="pending", security_surface_changed=False)
    for content in ["value = 1\nprint(value)\n", 'PATTERN = r"\\n"']:
        actual = candidate.model_copy(update={"file_contents": {"app.py": content}})
        assert _preserves_governed_facts(candidate.model_dump(mode="json"), actual)
    broken = candidate.model_copy(update={"file_contents": {"app.py": "value = 1\\nprint(value)\\n"}})
    assert not _preserves_governed_facts(candidate.model_dump(mode="json"), broken)


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
    assert requests[0]["prompt"].endswith(
        "Copy every candidate key and value exactly; do not omit schema-optional keys."
    )
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
