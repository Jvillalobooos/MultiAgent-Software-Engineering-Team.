"""Sanitized, classified diagnostics at the cloud HTTP boundary."""

from __future__ import annotations

import httpx
import pytest

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.models import ProductSpecification
from engineering_team.llm.cloud import CloudModelRuntime
from engineering_team.models.context import ContextEnvelope


def cloud_envelope() -> ContextEnvelope:
    return ContextEnvelope(
        agent=AgentRole.PRODUCT, current_task="classify requirement",
        state_projection={"requirement": "Add a health endpoint"},
        rag_evidence=[], tool_results=[], remediation_feedback=None,
        output_schema="", allowed_tools=[], model_profile="CLOUD_FALLBACK",
        projection_fingerprint="fixture-fingerprint",
    )


def product_candidate() -> ProductSpecification:
    return ProductSpecification(
        objective="Add a health endpoint", actors=["operator"],
        business_rules=["Return healthy status"], constraints=["Keep compatibility"],
        acceptance_criteria=["GET health returns 200"], nfrs=["Deterministic"],
        ambiguities=[], assumptions=[], source_requirement="Add a health endpoint",
    )


def _runtime(status: int, body: dict[str, object]) -> CloudModelRuntime:
    settings = Settings(
        cloud_enabled=True, local_first=False, gemini_api_key="fixture-key",
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    return CloudModelRuntime(settings, client=httpx.Client(transport=transport), primary=True)


def test_cloud_http_401_is_sanitized_and_classified() -> None:
    runtime = _runtime(401, {"error": {"message": "api key sk-secret is invalid"}})
    with pytest.raises(RuntimeError, match="authentication"):
        runtime.invoke_artifact(AgentRole.PRODUCT, cloud_envelope(), product_candidate())
    attempt = runtime.attempts[-1]
    assert attempt.http_status == 401
    assert attempt.error_category == "authentication"
    assert attempt.retryable is False
    assert "sk-secret" not in attempt.error


def test_cloud_http_404_is_model_unavailable_and_not_retryable() -> None:
    runtime = _runtime(404, {"error": {"message": "model not found"}})
    with pytest.raises(RuntimeError, match="model_unavailable"):
        runtime.invoke_artifact(AgentRole.PRODUCT, cloud_envelope(), product_candidate())
    attempt = runtime.attempts[-1]
    assert attempt.http_status == 404
    assert attempt.error_category == "model_unavailable"
    assert attempt.retryable is False


def test_cloud_http_429_is_rate_limit_and_retryable() -> None:
    runtime = _runtime(429, {"error": {"message": "too many requests"}})
    with pytest.raises(RuntimeError, match="rate_limit"):
        runtime.invoke_artifact(AgentRole.PRODUCT, cloud_envelope(), product_candidate())
    attempt = runtime.attempts[-1]
    assert attempt.http_status == 429
    assert attempt.error_category == "rate_limit"
    assert attempt.retryable is True


def test_cloud_http_503_is_provider_unavailable_and_retryable() -> None:
    runtime = _runtime(503, {"error": {"message": "service unavailable"}})
    with pytest.raises(RuntimeError, match="provider_unavailable"):
        runtime.invoke_artifact(AgentRole.PRODUCT, cloud_envelope(), product_candidate())
    attempt = runtime.attempts[-1]
    assert attempt.http_status == 503
    assert attempt.error_category == "provider_unavailable"
    assert attempt.retryable is True


def test_cloud_http_error_never_leaks_response_body() -> None:
    runtime = _runtime(401, {"error": {"message": "secret-token-value should never leak"}})
    with pytest.raises(RuntimeError):
        runtime.invoke_artifact(AgentRole.PRODUCT, cloud_envelope(), product_candidate())
    attempt = runtime.attempts[-1]
    assert "secret-token-value" not in attempt.error
    assert "should never leak" not in attempt.error
