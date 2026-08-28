
import json

import httpx
import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import (
    AttemptBudget,
    CloudBudget,
    CloudModelRuntime,
    CloudRouter,
    build_cloud_context,
    is_cloud_eligible,
)
from engineering_team.models.context import build_context


@pytest.mark.parametrize(
    ("role", "provider", "model"),
    [
        (AgentRole.PRODUCT, "google", "gemini-3.6-flash"),
        (AgentRole.ARCHITECTURE, "google", "gemini-3.6-flash"),
        (AgentRole.DEVELOPER, "google", "gemini-3.6-flash"),
        (AgentRole.SECURITY, "groq", "openai/gpt-oss-120b"),
        (AgentRole.TESTING, "groq", "openai/gpt-oss-20b"),
        (AgentRole.REVIEWER, "google", "gemini-3.6-flash"),
    ],
)
def test_cloud_mapping_is_fixed(role: AgentRole, provider: str, model: str) -> None:
    selection = CloudRouter(Settings(_env_file=None)).for_role(role)
    assert (selection.provider, selection.model) == (provider, model)


def test_cloud_router_walks_the_whole_gemini_chain_before_local_fallback() -> None:
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.PRODUCT)

    assert [(item.provider, item.model) for item in chain] == [
        ("google", "gemini-3.6-flash"),
        ("google", "gemini-3.5-flash"),
        ("google", "gemini-3.1-flash-lite"),
        ("google", "gemini-2.5-flash"),
        ("groq", "openai/gpt-oss-120b"),
    ]


def test_gemini_chain_is_configurable_and_keeps_the_role_model_first() -> None:
    settings = Settings(_env_file=None, gemini_models="gemini-2.5-flash, gemini-3.6-flash ,,")
    chain = CloudRouter(settings).selection_chain(AgentRole.PRODUCT)

    assert [(item.provider, item.model) for item in chain] == [
        ("google", "gemini-3.6-flash"),
        ("google", "gemini-2.5-flash"),
        ("groq", "openai/gpt-oss-120b"),
    ]


def test_developer_crosses_to_groq_after_every_gemini_model():
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.DEVELOPER)

    assert [(item.provider, item.model) for item in chain][-1] == ("groq", "openai/gpt-oss-120b")
    assert all(item.provider == "google" for item in chain[:-1])


def test_groq_backed_role_keeps_its_single_alternate():
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.TESTING)

    assert [(item.provider, item.model) for item in chain] == [
        ("groq", "openai/gpt-oss-20b"),
        ("groq", "openai/gpt-oss-120b"),
    ]


def test_tool_and_rag_errors_never_trigger_cloud() -> None:
    assert not is_cloud_eligible(ErrorCode.TOOL_ERROR)
    assert not is_cloud_eligible(ErrorCode.MCP_ERROR)
    assert not is_cloud_eligible(ErrorCode.RAG_ERROR)
    assert is_cloud_eligible(ErrorCode.LLM_QUALITY_ERROR)


def test_cloud_context_redacts_or_rejects_sensitive_payload() -> None:
    with pytest.raises(ValueError):
        build_cloud_context(AgentRole.PRODUCT, "task", "req", {"API_KEY": "x"})
    safe = build_cloud_context(
        AgentRole.PRODUCT, "task", "password recovery with single-use token", {"rule": "expire"}
    )
    assert "password recovery" in safe.relevant_requirement


def test_retry_repair_and_cloud_escalation_budgets_are_independent() -> None:
    settings = Settings(_env_file=None)
    attempts = AttemptBudget(settings)
    cloud = CloudBudget(settings)

    assert attempts.consume_retry("Product") is True
    assert attempts.consume_retry("Product") is False
    assert attempts.consume_repair("Product") is True
    assert attempts.consume_repair("Product") is False

    assert cloud.consume(AgentRole.PRODUCT) is True
    assert cloud.consume(AgentRole.PRODUCT) is False
    assert cloud.consume(AgentRole.ARCHITECTURE) is True
    assert cloud.consume(AgentRole.DEVELOPER) is True
    assert cloud.consume(AgentRole.SECURITY) is False
    assert cloud.run_count == 3


def test_cloud_runtime_validates_provider_response_and_marks_fallback() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)

    def handler(request):
        assert request.headers["x-goog-api-key"] == "configured-but-not-logged"
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": candidate.model_dump_json()}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        })

    settings = Settings(
        _env_file=None, cloud_enabled=True, gemini_api_key="configured-but-not-logged"
    )
    runtime = CloudModelRuntime(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    artifact, info = runtime.invoke_artifact(
        AgentRole.PRODUCT,
        envelope,
        candidate,
        fallback_reason=ErrorCode.LLM_QUALITY_ERROR.value,
    )

    assert artifact == candidate
    assert info.provider == "google"
    assert info.fallback_used is True
    assert info.fallback_reason == "LLM_QUALITY_ERROR"


def test_groq_cloud_runtime_uses_fixed_model_and_validates_response() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe code change")
    envelope = build_context(AgentRole.SECURITY, state, "Security")
    candidate = ProductAgent().execute(
        build_context(AgentRole.PRODUCT, state, "Product")
    )

    def handler(request):
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer configured-but-not-logged"
        assert body["model"] == "openai/gpt-oss-120b"
        return httpx.Response(200, json={
            "choices": [{"message": {"content": candidate.model_dump_json()}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    settings = Settings(
        _env_file=None, cloud_enabled=True, groq_api_key="configured-but-not-logged"
    )
    runtime = CloudModelRuntime(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    artifact, info = runtime.invoke_artifact(
        AgentRole.SECURITY,
        envelope,
        candidate,
        fallback_reason=ErrorCode.LLM_QUALITY_ERROR.value,
    )

    assert artifact == candidate
    assert info.provider == "groq"
    assert info.requested_model == "openai/gpt-oss-120b"


def test_cloud_provider_outage_is_normalized_without_secret_exposure() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)
    runtime = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key="never-print-this"),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(429, json={"error": "rate limited"})
        )),
    )

    with pytest.raises(RuntimeError, match="CLOUD_FALLBACK_UNAVAILABLE") as error:
        runtime.invoke_artifact(
            AgentRole.PRODUCT,
            envelope,
            candidate,
            fallback_reason=ErrorCode.LLM_AVAILABILITY_ERROR.value,
        )

    assert "never-print-this" not in str(error.value)
    assert runtime.budget.run_count == 1
