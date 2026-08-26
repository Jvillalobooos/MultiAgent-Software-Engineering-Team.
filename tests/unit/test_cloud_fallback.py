
import json

import httpx
import pytest

from engineering_team.agents.product import ProductAgent
from engineering_team.config import Settings
from engineering_team.contracts.enums import ActionMode, AgentRole, ErrorCode
from engineering_team.contracts.models import ImplementationResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import (
    GEMINI_INTERACTIONS_URL,
    AttemptBudget,
    CloudBudget,
    CloudModelRuntime,
    CloudRouter,
    build_cloud_context,
    extract_gemini_output_text,
    is_cloud_eligible,
)
from engineering_team.models.context import build_context


def _gemini_response(candidate) -> dict:
    """A realistic Interactions API response shape: steps -> model_output -> content -> text."""
    return {
        "steps": [
            {"type": "reasoning", "content": [{"type": "text", "text": "thinking..."}]},
            {
                "type": "model_output",
                "content": [{"type": "text", "text": candidate.model_dump_json()}],
            },
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }


@pytest.mark.parametrize(
    ("role", "provider", "model"),
    [
        (AgentRole.PRODUCT, "google", "gemini-3.7-flash"),
        (AgentRole.ARCHITECTURE, "google", "gemini-3.7-flash"),
        (AgentRole.DEVELOPER, "groq", "openai/gpt-oss-120b"),
        (AgentRole.SECURITY, "groq", "openai/gpt-oss-120b"),
        (AgentRole.TESTING, "groq", "openai/gpt-oss-20b"),
        (AgentRole.REVIEWER, "google", "gemini-3.7-flash"),
    ],
)
def test_cloud_mapping_is_fixed(role: AgentRole, provider: str, model: str) -> None:
    selection = CloudRouter(Settings(_env_file=None)).for_role(role)
    assert (selection.provider, selection.model) == (provider, model)


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
        return httpx.Response(200, json=_gemini_response(candidate))

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
    # Pydantic and governed-fact validation both actually ran to accept this artifact.
    assert info.structured_output_success is True


def test_gemini_payload_uses_interactions_api_and_omits_legacy_fields() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)
    captured: dict = {}
    captured_url = {}

    def handler(request):
        captured_url["url"] = str(request.url)
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_gemini_response(candidate))

    settings = Settings(
        _env_file=None, cloud_enabled=True, gemini_api_key="configured-but-not-logged"
    )
    runtime = CloudModelRuntime(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert captured_url["url"] == GEMINI_INTERACTIONS_URL
    assert captured_url["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert captured["model"] == "gemini-3.7-flash"
    assert isinstance(captured["system_instruction"], str) and captured["system_instruction"]
    assert isinstance(captured["input"], str) and captured["input"]
    assert captured["store"] is False
    response_format = captured["response_format"]
    assert response_format["type"] == "text"
    assert response_format["mime_type"] == "application/json"
    assert response_format["schema"]["type"] == "object"
    assert "properties" in response_format["schema"]
    # Legacy/deprecated shapes and sampling parameters must not appear anywhere.
    assert "generationConfig" not in captured
    assert "responseJsonSchema" not in json.dumps(captured)
    assert "responseSchema" not in json.dumps(captured)
    assert "responseMimeType" not in json.dumps(captured)
    assert "temperature" not in captured
    assert "top_p" not in captured
    assert "top_k" not in captured
    assert "candidate_count" not in captured


def test_extract_gemini_output_text_finds_the_model_output_step() -> None:
    payload = {
        "steps": [
            {"type": "reasoning", "content": [{"type": "text", "text": "internal"}]},
            {"type": "model_output", "content": [{"type": "text", "text": '{"a": 1}'}]},
        ],
    }

    assert extract_gemini_output_text(payload) == '{"a": 1}'


def test_extract_gemini_output_text_raises_on_missing_model_output_step() -> None:
    with pytest.raises(ValueError, match="model_output"):
        extract_gemini_output_text({"steps": [{"type": "reasoning", "content": []}]})


def test_missing_gemini_model_output_step_is_classified_llm_quality_error() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)
    runtime = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key="configured"),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"steps": []})
        )),
    )

    with pytest.raises(RuntimeError, match="LLM_QUALITY_ERROR") as error:
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert "model_output" in str(error.value)


def test_gemini_timeout_is_classified_agent_timeout_and_records_latency() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)

    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    runtime = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key="configured"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RuntimeError, match="AGENT_TIMEOUT"):
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert runtime.attempts[-1].latency_ms >= 0
    assert runtime.attempts[-1].error is not None
    assert runtime.attempts[-1].error.startswith("AGENT_TIMEOUT")


def test_cloud_first_primary_failure_is_not_labeled_fallback_unavailable() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)
    runtime = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key="never-print-this"),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(429, text="rate limited")
        )),
    )

    with pytest.raises(RuntimeError, match="LLM_AVAILABILITY_ERROR") as error:
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    assert "CLOUD_FALLBACK_UNAVAILABLE" not in str(error.value)
    assert "429" in str(error.value)


def test_groq_cloud_runtime_uses_fixed_model_and_validates_response() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe code change")
    envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
    candidate = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=[],
        diff="NO-OP: no inspected evidence", evidence=["mcp://repository/list_files"],
        validation_result="no-op: nothing inspected",
    )

    def handler(request):
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer configured-but-not-logged"
        assert body["model"] == "openai/gpt-oss-120b"
        plan = {"mutations": [], "no_mutation_reason": "insufficient inspected evidence", "blocker": None}
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps(plan)}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    settings = Settings(
        _env_file=None, cloud_enabled=True, groq_api_key="configured-but-not-logged"
    )
    runtime = CloudModelRuntime(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    artifact, info = runtime.invoke_artifact(
        AgentRole.DEVELOPER,
        envelope,
        candidate,
        fallback_reason=ErrorCode.LLM_QUALITY_ERROR.value,
    )

    assert artifact.mutations == []
    assert artifact.changed_files == candidate.changed_files
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
    # The safe HTTP status/body is captured from the SAME response, bounded and redacted.
    assert "HTTP 429" in str(error.value)
    assert "rate limited" in str(error.value)
    assert runtime.attempts[-1].latency_ms >= 0
    assert runtime.attempts[-1].error is not None
    assert "HTTP 429" in runtime.attempts[-1].error


def test_gemini_error_body_is_redacted_and_bounded() -> None:
    state = EngineeringState(run_id="cloud", requirement="safe change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)
    secret = "sk-super-secret-leak-me-not"
    long_body = json.dumps({
        "error": {"message": "bad request", "leaked_key": f"api_key={secret}", "pad": "x" * 2000},
    })
    runtime = CloudModelRuntime(
        Settings(_env_file=None, cloud_enabled=True, gemini_api_key=secret),
        client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(400, text=long_body)
        )),
    )

    with pytest.raises(RuntimeError) as error:
        runtime.invoke_artifact(AgentRole.PRODUCT, envelope, candidate, mode="primary")

    message = str(error.value)
    assert secret not in message
    assert len(message) < 700
