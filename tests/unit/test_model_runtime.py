import json

import httpx

from engineering_team.config import Settings
from engineering_team.contracts.enums import ActionMode, AgentRole
from engineering_team.contracts.models import ArchitectureProposal, ImplementationResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.runtime import LocalModelRuntime, _preserves_governed_facts
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
    assert requests[0]["system"] != requests[0]["prompt"]
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


def test_semantic_guard_rejects_invented_source_and_material_developer_change() -> None:
    architecture = ArchitectureProposal(
        components=["API"], apis=[], data_changes=[], integrations=[], dependencies=[],
        decisions=[], risks=[], impact="safe", evidence_references=["retrieved:1"],
    )
    invented = architecture.model_copy(
        update={"evidence_references": ["retrieved:1", "invented:99"]}
    )
    implementation = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=[], diff="", evidence=["design"],
        validation_result="not applied", security_surface_changed=False,
    )
    fabricated = implementation.model_copy(update={
        "action_mode": ActionMode.APPLIED, "changed_files": ["app.py"],
        "diff": "+ unsafe", "validation_result": "passed",
    })

    assert not _preserves_governed_facts(architecture.model_dump(mode="json"), invented)
    assert not _preserves_governed_facts(implementation.model_dump(mode="json"), fabricated)
