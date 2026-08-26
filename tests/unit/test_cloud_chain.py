"""Deterministic primary -> secondary cloud -> local provider chain."""

import json

import httpx
import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import ActionMode, AgentRole, ErrorCode, ModelPriority
from engineering_team.contracts.models import ImplementationResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import GEMINI_INTERACTIONS_URL, CloudModelRuntime
from engineering_team.llm.priority import resolve_runtime_order
from engineering_team.models.context import build_context


def _gemini_ok(candidate) -> httpx.Response:
    return _gemini_ok_raw(candidate.model_dump_json())


def _gemini_ok_raw(raw_json: str) -> httpx.Response:
    return httpx.Response(200, json={
        "steps": [{
            "type": "model_output",
            "content": [{"type": "text", "text": raw_json}],
        }],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    })


def _groq_ok(payload: dict) -> httpx.Response:
    return httpx.Response(200, json={
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    })


def _is_gemini(request: httpx.Request) -> bool:
    return str(request.url) == GEMINI_INTERACTIONS_URL


def _product_candidate():
    state = EngineeringState(run_id="chain", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    return envelope, ProductAgent().execute(envelope)


def _developer_candidate():
    state = EngineeringState(run_id="chain-dev", requirement="safe code change")
    envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=[],
        diff="NO-OP: no inspected evidence", evidence=["mcp://repository/list_files"],
        validation_result="no-op: nothing inspected",
    )
    return envelope, candidate


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None, cloud_enabled=True,
        gemini_api_key="gemini-key", groq_api_key="groq-key", **overrides,
    )


# A. Gemini primary succeeds -> Groq not called -> Ollama not called.
def test_gemini_primary_success_never_calls_groq() -> None:
    envelope, candidate = _product_candidate()
    calls = {"gemini": 0, "groq": 0}

    def handler(request):
        if _is_gemini(request):
            calls["gemini"] += 1
            return _gemini_ok(candidate)
        calls["groq"] += 1
        return _groq_ok(candidate.model_dump(mode="json"))

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    _artifact, info = runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert calls == {"gemini": 1, "groq": 0}
    assert info.provider == "google"
    assert info.fallback_used is False


# B. Gemini primary HTTP 500 availability -> Groq secondary called exactly once -> Ollama not called.
def test_gemini_availability_failure_escalates_to_groq_secondary_once() -> None:
    envelope, candidate = _product_candidate()
    calls = {"gemini": 0, "groq": 0}

    def handler(request):
        if _is_gemini(request):
            calls["gemini"] += 1
            return httpx.Response(500, json={"error": {"code": "api_error", "message": "high demand"}})
        calls["groq"] += 1
        return _groq_ok(candidate.model_dump(mode="json"))

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    _artifact, info = runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert calls == {"gemini": 1, "groq": 1}
    assert info.provider == "groq"
    assert info.fallback_used is True
    assert info.fallback_reason == ErrorCode.LLM_AVAILABILITY_ERROR.value
    assert len(runtime.attempts) == 2
    assert runtime.attempts[0].error is not None and "LLM_AVAILABILITY_ERROR" in runtime.attempts[0].error


# C. Gemini timeout -> Groq secondary exactly once.
def test_gemini_timeout_escalates_to_groq_secondary_once() -> None:
    envelope, candidate = _product_candidate()
    calls = {"gemini": 0, "groq": 0}

    def handler(request):
        if _is_gemini(request):
            calls["gemini"] += 1
            raise httpx.ReadTimeout("timed out", request=request)
        calls["groq"] += 1
        return _groq_ok(candidate.model_dump(mode="json"))

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    _artifact, info = runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert calls == {"gemini": 1, "groq": 1}
    assert runtime.attempts[0].error.startswith("AGENT_TIMEOUT")
    assert info.provider == "groq"


# D. Developer: Groq primary succeeds -> Gemini and Ollama not called.
def test_groq_primary_success_never_calls_gemini_for_developer() -> None:
    envelope, candidate = _developer_candidate()
    calls = {"gemini": 0, "groq": 0}
    plan = {"mutations": [], "no_mutation_reason": "insufficient evidence", "blocker": None}

    def handler(request):
        if _is_gemini(request):
            calls["gemini"] += 1
            return _gemini_ok(candidate)
        calls["groq"] += 1
        return _groq_ok(plan)

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    _artifact, info = runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate, mode="primary")

    assert calls == {"gemini": 0, "groq": 1}
    assert info.provider == "groq"


# E. Groq primary availability failure -> Gemini secondary -> Ollama not called if Gemini succeeds.
def test_groq_availability_failure_escalates_to_gemini_secondary() -> None:
    envelope, candidate = _developer_candidate()
    calls = {"gemini": 0, "groq": 0}
    plan = {"mutations": [], "no_mutation_reason": "insufficient evidence", "blocker": None}

    def handler(request):
        if _is_gemini(request):
            calls["gemini"] += 1
            return _gemini_ok_raw(json.dumps(plan))
        calls["groq"] += 1
        return httpx.Response(503, text="groq unavailable")

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    _artifact, info = runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate, mode="primary")

    assert calls == {"gemini": 1, "groq": 1}
    assert info.provider == "google"
    assert info.fallback_used is True


# F. Both cloud providers unavailable -> caller falls to local exactly once.
def test_both_cloud_providers_failing_leaves_local_as_the_only_remaining_fallback() -> None:
    envelope, candidate = _product_candidate()

    def handler(request):
        return httpx.Response(500, json={"error": "down"})

    cloud = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    class LocalStub:
        def __init__(self):
            self.attempts = []
            self.calls = 0

        def invoke_artifact(self, role, envelope, candidate, *, mode="fallback", fallback_reason=None, start_index=0):
            self.calls += 1
            info_kwargs = {
                "agent": role, "provider": "ollama", "requested_model": "qwen3.5:9b",
                "actual_model": "qwen3.5:9b", "model_profile": "LOCAL",
                "fallback_used": True, "fallback_reason": fallback_reason,
                "latency_ms": 1, "structured_output_success": True,
            }
            from engineering_team.contracts.models import ModelExecutionInfo
            info = ModelExecutionInfo(**info_kwargs)
            self.attempts.append(info)
            return candidate, info

    order = resolve_runtime_order(ModelPriority.CLOUD_FIRST, LocalStub(), cloud)
    with pytest.raises(RuntimeError):
        order.primary.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")
    _artifact, info = order.fallback.invoke_artifact(
        AgentRole.PRODUCT, envelope, candidate, mode="fallback",
        fallback_reason=ErrorCode.LLM_AVAILABILITY_ERROR.value,
    )
    assert order.fallback.calls == 1
    assert info.provider == "ollama"


# G. CLOUD_ONLY: both cloud providers fail -> governed terminal, Ollama never invoked.
def test_cloud_only_never_resolves_a_local_fallback_even_when_both_providers_fail() -> None:
    order = resolve_runtime_order(ModelPriority.CLOUD_ONLY, object(), object())

    assert order.fallback is None
    assert order.primary_is_cloud is True


# H. LOCAL_ONLY: no cloud HTTP calls (resolved order never touches the cloud runtime).
def test_local_only_never_resolves_a_cloud_primary_or_fallback() -> None:
    order = resolve_runtime_order(ModelPriority.LOCAL_ONLY, object(), object())

    assert order.primary_is_cloud is False
    assert order.fallback is None


# J. Gemini HTTP 500 high-demand response is classified LLM_AVAILABILITY_ERROR
# (the exact real-world case observed during LIVE cloud-provider verification),
# and immediately advances to the secondary cloud provider rather than raising.
def test_gemini_high_demand_500_is_classified_llm_availability_error() -> None:
    envelope, candidate = _product_candidate()

    def handler(request):
        if _is_gemini(request):
            return httpx.Response(500, json={
                "error": {"code": "api_error", "message": "gemini-3.7-flash is currently experiencing high demand"},
            })
        return _groq_ok(candidate.model_dump(mode="json"))

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    _artifact, info = runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert info.provider == "groq"
    assert runtime.attempts[0].provider == "google"
    assert runtime.attempts[0].error is not None
    assert runtime.attempts[0].error.startswith(ErrorCode.LLM_AVAILABILITY_ERROR.value)
    assert "500" in runtime.attempts[0].error


# K. Security/Test/MCP/RAG failures do NOT trigger provider switching (routing-level contract).
def test_workflow_domain_errors_are_never_cloud_eligible() -> None:
    from engineering_team.llm.cloud import is_cloud_eligible

    assert not is_cloud_eligible(ErrorCode.MCP_ERROR)
    assert not is_cloud_eligible(ErrorCode.TOOL_ERROR)
    assert not is_cloud_eligible(ErrorCode.RAG_ERROR)


# I. Provider fallback attempts within one invoke_artifact call are bounded (each
# provider attempted at most once) and are a pure runtime-level concern, entirely
# separate from EngineeringState.iteration (which the graph only advances on an
# actual Reviewer rejection - see tests/integration/test_workflow.py for the
# end-to-end proof that a provider escalation never bumps `iteration`).
def test_each_provider_is_attempted_at_most_once_per_invocation() -> None:
    envelope, candidate = _product_candidate()
    calls = {"gemini": 0, "groq": 0}

    def handler(request):
        if _is_gemini(request):
            calls["gemini"] += 1
            return httpx.Response(500, json={"error": "down"})
        calls["groq"] += 1
        return httpx.Response(500, text="also down")

    runtime = CloudModelRuntime(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(RuntimeError):
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert calls == {"gemini": 1, "groq": 1}
