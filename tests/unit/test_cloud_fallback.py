
import json

import httpx
import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import (
    _CLOUD_MAP,
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
        (AgentRole.DEVELOPER, "google", "gemini-3.1-pro-preview"),
        (AgentRole.SECURITY, "groq", "openai/gpt-oss-120b"),
        (AgentRole.TESTING, "groq", "openai/gpt-oss-20b"),
        (AgentRole.REVIEWER, "google", "gemini-3.6-flash"),
    ],
)
def test_cloud_mapping_is_fixed(role: AgentRole, provider: str, model: str) -> None:
    selection = CloudRouter(Settings(_env_file=None)).for_role(role)
    assert (selection.provider, selection.model) == (provider, model)


def test_cross_provider_escape_sits_second_not_last() -> None:
    """Gemini quota is per project, so a 429 on one Gemini model predicts a 429 on the
    next. Walking the whole Gemini pool first spends every attempt inside the same
    failing quota domain."""
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.PRODUCT)

    assert [(item.provider, item.model) for item in chain] == [
        ("google", "gemini-3.6-flash"),
        ("groq", "openai/gpt-oss-120b"),
        ("google", "gemini-3.5-flash"),
        ("google", "gemini-3.7-flash"),
        ("google", "gemini-flash-latest"),
    ]


def test_developer_leads_with_a_model_that_answers_and_skips_the_escape() -> None:
    """The pro tier stays in the pool but behind the two models that actually answer:
    leading with one that returns 429 on every call spends a round trip for nothing.
    Groq is dropped from this role because the Developer payload exceeds its
    tokens-per-minute cap (HTTP 413)."""
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.DEVELOPER)

    assert (chain[0].provider, chain[0].model) == ("google", "gemini-3.6-flash")
    assert all(item.provider == "google" for item in chain)
    assert "gemini-3.1-pro-preview" in {item.model for item in chain}


def test_models_that_never_answer_are_not_in_any_pool() -> None:
    """gemini-2.5-flash returns HTTP 404 'no longer available to new users' for every
    request shape, and gemini-3.1-flash-lite failed schema validation on 40% of the
    responses it delivered. Both are removed rather than demoted."""
    router = CloudRouter(Settings(_env_file=None))
    dead = {"gemini-2.5-flash", "gemini-3.1-flash-lite"}
    for role in (AgentRole.PRODUCT, AgentRole.ARCHITECTURE, AgentRole.DEVELOPER,
                 AgentRole.SECURITY, AgentRole.TESTING, AgentRole.REVIEWER):
        assert not ({i.model for i in router.selection_chain(role)} & dead)


def test_pools_are_configurable_per_role_and_deduplicated() -> None:
    settings = Settings(
        _env_file=None,
        gemini_models="gemini-2.5-flash, gemini-2.5-flash ,, gemini-3.6-flash",
        gemini_developer_models="gemini-pro-latest",
        cloud_escape_model="openai/gpt-oss-20b",
    )
    router = CloudRouter(settings)

    assert [(i.provider, i.model) for i in router.selection_chain(AgentRole.PRODUCT)] == [
        ("google", "gemini-2.5-flash"),
        ("groq", "openai/gpt-oss-20b"),
        ("google", "gemini-3.6-flash"),
    ]
    # Developer is excluded from the escape by default, so its chain is Google only.
    assert [(i.provider, i.model) for i in router.selection_chain(AgentRole.DEVELOPER)] == [
        ("google", "gemini-pro-latest"),
    ]


def test_no_chain_ever_retries_the_same_model_twice() -> None:
    router = CloudRouter(Settings(_env_file=None))
    for role in AgentRole:
        chain = router.selection_chain(role) if role in _CLOUD_MAP else ()
        models = [(i.provider, i.model) for i in chain]
        assert len(set(models)) == len(models), f"{role} retries a model: {models}"


def test_groq_backed_role_never_retries_its_own_primary_model() -> None:
    """"openai/gpt-oss-120b" also ends with "20b", so a suffix test resolved Security's
    alternate back to its own primary and wasted the attempt."""
    chain = CloudRouter(Settings(_env_file=None)).selection_chain(AgentRole.SECURITY)

    assert [(item.provider, item.model) for item in chain] == [
        ("groq", "openai/gpt-oss-120b"),
        ("groq", "openai/gpt-oss-20b"),
    ]
    assert len({item.model for item in chain}) == len(chain)


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
