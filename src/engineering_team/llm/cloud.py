"""Bounded cloud contingency routing; not normal model selection."""

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.models import CloudFallbackContext, ModelExecutionInfo
from engineering_team.guardrails.secrets import require_safe_cloud_context
from engineering_team.llm.prompting import build_role_prompts, governed_output_schema
from engineering_team.models.context import ContextEnvelope

from .registry import ModelSelection
from .runtime import _preserves_governed_facts

_CLOUD_MAP = {
    AgentRole.PRODUCT: ("google", "gemini-3.7-flash"),
    AgentRole.ARCHITECTURE: ("google", "gemini-3.7-flash"),
    AgentRole.DEVELOPER: ("groq", "openai/gpt-oss-120b"),
    AgentRole.SECURITY: ("groq", "openai/gpt-oss-120b"),
    AgentRole.TESTING: ("groq", "openai/gpt-oss-20b"),
    AgentRole.REVIEWER: ("google", "gemini-3.7-flash"),
}


@dataclass
class AttemptBudget:
    settings: Settings
    retries: dict[str, int] = field(default_factory=dict)
    repairs: dict[str, int] = field(default_factory=dict)

    def consume_retry(self, stage: str) -> bool:
        used = self.retries.get(stage, 0)
        if used >= self.settings.max_local_retries:
            return False
        self.retries[stage] = used + 1
        return True

    def consume_repair(self, stage: str) -> bool:
        used = self.repairs.get(stage, 0)
        if used >= self.settings.max_local_repairs:
            return False
        self.repairs[stage] = used + 1
        return True


@dataclass
class CloudBudget:
    """Bounds cloud usage when cloud is a *fallback*.

    When cloud is the configured primary runtime (``cloud_first``), the caps
    below describe an emergency-contingency budget, not the steady-state
    workload of six agents per run, so ``unlimited`` disables the cap while
    still recording counts for observability/telemetry.
    """

    settings: Settings
    by_agent: dict[AgentRole, int] = field(default_factory=dict)
    run_count: int = 0
    unlimited: bool = False

    def consume(self, role: AgentRole) -> bool:
        if not self.unlimited:
            if self.run_count >= self.settings.max_cloud_escalations_per_run:
                return False
            used = self.by_agent.get(role, 0)
            if used >= self.settings.max_cloud_escalations_per_agent:
                return False
        self.by_agent[role] = self.by_agent.get(role, 0) + 1
        self.run_count += 1
        return True


class CloudRouter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def for_role(self, role: AgentRole) -> ModelSelection:
        provider, model = _CLOUD_MAP[role]
        return ModelSelection(role, "CLOUD_FALLBACK", provider, model)

    def enabled_for(self, role: AgentRole) -> bool:
        key = (
            self._settings.gemini_api_key
            if _CLOUD_MAP[role][0] == "google"
            else self._settings.groq_api_key
        )
        return self._settings.cloud_enabled and bool(key)


def _http_category(status: int) -> tuple[str, bool]:
    """Classify a provider HTTP status into a sanitized, actionable cause.

    Never inspect the response body here: only the status code is safe to
    surface without risking a leaked credential or provider-specific detail.
    """
    if status in {401, 403}:
        return "authentication", False
    if status == 404:
        return "model_unavailable", False
    if status == 429:
        return "rate_limit", True
    if status >= 500:
        return "provider_unavailable", True
    return "request_rejected", False


def is_cloud_eligible(error: ErrorCode) -> bool:
    return error in {
        ErrorCode.LLM_AVAILABILITY_ERROR,
        ErrorCode.LLM_QUALITY_ERROR,
        ErrorCode.SECURITY_CONFLICT,
        ErrorCode.AGENT_TIMEOUT,
    }


def build_cloud_context(
    agent: AgentRole,
    task: str,
    requirement: str,
    structured_input: dict[str, object],
    **kwargs: object,
) -> CloudFallbackContext:
    require_safe_cloud_context(task)
    require_safe_cloud_context(requirement)
    require_safe_cloud_context(structured_input)
    require_safe_cloud_context(kwargs)
    return CloudFallbackContext(
        agent=agent,
        task=task,
        relevant_requirement=requirement,
        structured_input=structured_input,
        validation_error=kwargs.get("validation_error")
        if isinstance(kwargs.get("validation_error"), str)
        else None,
        rag_fragments=list(kwargs.get("rag_fragments", [])),
        code_fragments=list(kwargs.get("code_fragments", [])),
        deterministic_evidence=list(kwargs.get("deterministic_evidence", [])),
    )


class CloudModelRuntime:
    """Schema-constrained Gemini/Groq runtime.

    Usable either as the *fallback* runtime (bounded by ``CloudBudget``, the
    historical role) or as the *primary* runtime for a cloud-first
    configuration (``primary=True``), in which case the per-agent/per-run
    escalation caps are disabled since six agents per run is the expected
    steady-state workload, not an emergency contingency.
    """

    def __init__(
        self, settings: Settings, *, client: httpx.Client | None = None,
        trace: Any | None = None, primary: bool = False,
    ) -> None:
        self.settings = settings
        self.router = CloudRouter(settings)
        self.budget = CloudBudget(settings, unlimited=primary)
        self.client = client
        self.trace = trace
        self.primary = primary
        self.attempts: list[ModelExecutionInfo] = []

    def invoke_artifact(
        self,
        role: AgentRole,
        envelope: ContextEnvelope,
        candidate: BaseModel,
        *,
        fallback_reason: str = "CLOUD_FIRST",
    ) -> tuple[BaseModel, ModelExecutionInfo]:
        selection = self.router.for_role(role)
        if not self.router.enabled_for(role) or not self.budget.consume(role):
            raise RuntimeError("CLOUD_FALLBACK_UNAVAILABLE: disabled, missing credential, or budget")
        candidate_dict = candidate.model_dump(mode="json")
        output_schema = governed_output_schema(type(candidate))
        system_prompt, user_prompt = build_role_prompts(
            role, envelope, output_schema, candidate_dict
        )
        safe_context = build_cloud_context(
            role, envelope.current_task,
            str(envelope.state_projection.get("requirement", "")),
            {"candidate": candidate_dict},
            deterministic_evidence=[item.chunk_id for item in envelope.rag_evidence],
        )
        require_safe_cloud_context(system_prompt)
        require_safe_cloud_context(user_prompt)
        owns_client = self.client is None
        client = self.client or httpx.Client(timeout=self.settings.llm_timeout_seconds)
        started = time.perf_counter()
        try:
            if selection.provider == "google":
                response = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{selection.model}:generateContent",
                    headers={"x-goog-api-key": self.settings.gemini_api_key or ""},
                    json={
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                        "generationConfig": {
                            "temperature": 0,
                            "responseMimeType": "application/json",
                            "responseJsonSchema": output_schema,
                        },
                    },
                )
                response.raise_for_status()
                payload = response.json()
                raw = payload["candidates"][0]["content"]["parts"][0]["text"]
                usage = payload.get("usageMetadata")
            else:
                response = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.settings.groq_api_key or ''}"},
                    json={
                        "model": selection.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                payload = response.json()
                raw = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage")
            artifact = type(candidate).model_validate_json(raw)
            if not _preserves_governed_facts(candidate.model_dump(mode="json"), artifact):
                raise ValueError("governed artifact contradiction")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            category, retryable = _http_category(status)
            error = f"CLOUD_FALLBACK_UNAVAILABLE: {category} (HTTP {status})"
            info = ModelExecutionInfo(
                agent=role, provider=selection.provider, requested_model=selection.model,
                actual_model=None, model_profile=selection.model_profile,
                fallback_used=True, fallback_reason=fallback_reason, degraded=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
                structured_output_success=False, error=error,
                http_status=status, error_category=category, retryable=retryable,
            )
            self.attempts.append(info)
            if self.trace is not None:
                self.trace.record(
                    f"{role.value} cloud {'primary' if self.primary else 'fallback'}",
                    as_type="generation",
                    metadata=info.model_dump(mode="json"), level="ERROR",
                    status_message=error,
                )
            raise RuntimeError(error) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            error = f"CLOUD_FALLBACK_UNAVAILABLE: {type(exc).__name__}"
            info = ModelExecutionInfo(
                agent=role, provider=selection.provider, requested_model=selection.model,
                actual_model=None, model_profile=selection.model_profile,
                fallback_used=True, fallback_reason=fallback_reason, degraded=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
                structured_output_success=False, error=error,
            )
            self.attempts.append(info)
            if self.trace is not None:
                self.trace.record(
                    f"{role.value} cloud {'primary' if self.primary else 'fallback'}",
                    as_type="generation",
                    metadata=info.model_dump(mode="json"), level="ERROR",
                    status_message=error,
                )
            raise RuntimeError(error) from exc
        finally:
            if owns_client:
                client.close()
        info = ModelExecutionInfo(
            agent=role, provider=selection.provider, requested_model=selection.model,
            actual_model=selection.model, model_profile=selection.model_profile,
            fallback_used=True, fallback_reason=fallback_reason,
            latency_ms=int((time.perf_counter() - started) * 1000), usage=usage,
            structured_output_success=True,
        )
        self.attempts.append(info)
        if self.trace is not None:
            self.trace.record(
                f"{role.value} cloud {'primary' if self.primary else 'fallback'}",
                as_type="generation",
                input={"system_prompt": system_prompt, "user_prompt": user_prompt},
                output={"response": raw}, model=selection.model,
                metadata={
                    **info.model_dump(mode="json"),
                    "safe_context": safe_context.model_dump(mode="json"),
                },
                usage_details=usage,
            )
        return artifact, info
