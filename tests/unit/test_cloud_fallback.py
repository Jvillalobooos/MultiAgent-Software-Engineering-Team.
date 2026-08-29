
import json

import httpx
import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import (
    _CLOUD_MAP,
    _OPENAI_COMPATIBLE,
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
        (AgentRole.PRODUCT, "groq", "openai/gpt-oss-120b"),
        (AgentRole.ARCHITECTURE, "mistral", "mistral-medium-latest"),
        (AgentRole.DEVELOPER, "mistral", "codestral-latest"),
        (AgentRole.SECURITY, "openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        (AgentRole.TESTING, "groq", "openai/gpt-oss-20b"),
        (AgentRole.REVIEWER, "groq", "openai/gpt-oss-120b"),
    ],
)
def test_cloud_mapping_is_fixed(role: AgentRole, provider: str, model: str) -> None:
    selection = CloudRouter(Settings(_env_file=None)).for_role(role)
    assert (selection.provider, selection.model) == (provider, model)


def test_primary_models_span_three_providers() -> None:
    """Distribute load without promoting a repeatedly throttled fourth provider."""
    router = CloudRouter(Settings(_env_file=None))
    roles = (AgentRole.PRODUCT, AgentRole.ARCHITECTURE, AgentRole.DEVELOPER, AgentRole.SECURITY)
    primaries = [router.selection_chain(role)[0].provider for role in roles]
    assert len(set(primaries)) >= 3, f"providers concentrated: {primaries}"


def test_the_first_fallback_always_leaves_the_failing_provider() -> None:
    """Provider diversity limits correlated outages; quotas may also be model scoped."""
    router = CloudRouter(Settings(_env_file=None))
    for role in (AgentRole.PRODUCT, AgentRole.ARCHITECTURE, AgentRole.DEVELOPER, AgentRole.SECURITY):
        chain = router.selection_chain(role)
        assert chain[0].provider != chain[1].provider, f"{role} retries its own provider"


def test_developer_leads_with_a_verified_coder_and_crosses_providers() -> None:
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.DEVELOPER)
    assert (chain[0].provider, chain[0].model) == ("mistral", "codestral-latest")
    assert (chain[1].provider, chain[1].model) == ("groq", "openai/gpt-oss-120b")
    assert chain[-1].model == "gemini-3.5-flash"
    assert ("mistral", "mistral-small-latest") in {(item.provider, item.model) for item in chain}
    assert all(item.model != "mistral-medium-latest" for item in chain)


def test_models_verified_unusable_are_absent_from_every_chain() -> None:
    """Each of these was probed with the real request shape and answered 404, 402, or
    malformed JSON. Appearing in a catalogue is not evidence a model is callable."""
    router = CloudRouter(Settings(_env_file=None))
    dead = {
        "gemini-2.5-flash", "gemini-3.1-flash-lite",
        "openai/gpt-oss-120b:free", "nvidia/nemotron-3-ultra-550b-a55b:free",
        "thinkingmachines/inkling:free", "z-ai/glm-5.2:free",
        "ministral-3b-latest", "mistral-large-latest",
        "qwen/qwen3.6-27b", "cohere/north-mini-code:free",
        "devstral-latest", "minimax/minimax-m3:free",
    }
    for role in AgentRole:
        assert not ({item.model for item in router.selection_chain(role)} & dead)


def test_each_role_has_at_least_three_provider_options() -> None:
    """Do not add a failing model just to fill a provider slot."""
    router = CloudRouter(Settings(_env_file=None))
    for role in (AgentRole.PRODUCT, AgentRole.ARCHITECTURE, AgentRole.DEVELOPER, AgentRole.SECURITY):
        providers = {item.provider for item in router.selection_chain(role)}
        assert len(providers) >= 3, f"{role} only reaches {providers}"


def test_a_chain_can_be_overridden_per_role_from_settings() -> None:
    settings = Settings(_env_file=None,
                        cloud_chain_developer="groq:qwen/qwen3.6-27b, openrouter:openai/gpt-oss-120b")
    chain = CloudRouter(settings).selection_chain(AgentRole.DEVELOPER)
    assert [(i.provider, i.model) for i in chain] == [
        ("groq", "qwen/qwen3.6-27b"),
        ("openrouter", "openai/gpt-oss-120b"),
    ]


def test_a_provider_without_a_credential_is_skipped_not_fatal() -> None:
    settings = Settings(_env_file=None, cloud_enabled=True, groq_api_key="fixture")
    router = CloudRouter(settings)
    chain = router.selection_chain(AgentRole.DEVELOPER)
    usable = [item for item in chain if router.enabled_for(item)]
    assert usable and all(item.provider == "groq" for item in usable)


def test_sambanova_is_gone_entirely() -> None:
    """All seven models in its catalogue answer HTTP 402 on this account: there is no
    free tier, so the provider was removed rather than demoted."""
    router = CloudRouter(Settings(_env_file=None))
    for role in AgentRole:
        assert all(i.provider != "sambanova" for i in router.selection_chain(role))
    assert "sambanova" not in _OPENAI_COMPATIBLE


def test_no_chain_ever_retries_the_same_model_twice() -> None:
    router = CloudRouter(Settings(_env_file=None))
    for role in AgentRole:
        chain = router.selection_chain(role) if role in _CLOUD_MAP else ()
        models = [(i.provider, i.model) for i in chain]
        assert len(set(models)) == len(models), f"{role} retries a model: {models}"


def test_security_crosses_providers_instead_of_retrying_groq() -> None:
    """Security used to hold two Groq models whose suffix test resolved the alternate
    back to its own primary. It now leaves the provider on the first fallback."""
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.SECURITY)

    assert (chain[0].provider, chain[0].model) == (
        "openrouter", "nvidia/nemotron-3-super-120b-a12b:free")
    assert chain[1].provider == "groq"
    assert len({(i.provider, i.model) for i in chain}) == len(chain)


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
