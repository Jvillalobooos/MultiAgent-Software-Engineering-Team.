"""Cloud model routing: primary cloud -> secondary cloud -> bounded local fallback."""

import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ValidationError

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.models import CloudFallbackContext, ModelExecutionInfo
from engineering_team.guardrails.secrets import redact_secrets, require_safe_cloud_context
from engineering_team.models.context import ContextEnvelope

from .registry import ModelSelection
from .runtime import (
    _governed_output_schema,
    _invocation_policy,
    build_prompts,
    merge_role_artifact,
    preserves_governed_facts,
    role_schema,
)

# Each role's deterministic two-provider cloud chain: primary, then secondary.
# A temporary capacity failure on one approved cloud provider must not force
# slow local inference while the other approved cloud provider is available.
_CLOUD_CHAIN: dict[AgentRole, list[tuple[str, str]]] = {
    AgentRole.PRODUCT: [("google", "gemini-3.7-flash"), ("groq", "openai/gpt-oss-120b")],
    AgentRole.ARCHITECTURE: [("google", "gemini-3.7-flash"), ("groq", "openai/gpt-oss-20b")],
    AgentRole.DEVELOPER: [("groq", "openai/gpt-oss-120b"), ("google", "gemini-3.7-flash")],
    AgentRole.SECURITY: [("groq", "openai/gpt-oss-120b"), ("google", "gemini-3.7-flash")],
    AgentRole.TESTING: [("groq", "openai/gpt-oss-20b"), ("google", "gemini-3.7-flash")],
    AgentRole.REVIEWER: [("google", "gemini-3.7-flash"), ("groq", "openai/gpt-oss-120b")],
}
_CLOUD_PROFILES = ("CLOUD_PRIMARY", "CLOUD_SECONDARY")


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
    """Bounds every provider FALLBACK step (including secondary-cloud escalation);
    the single free primary-cloud attempt never consumes it."""

    settings: Settings
    by_agent: dict[AgentRole, int] = field(default_factory=dict)
    run_count: int = 0

    def consume(self, role: AgentRole) -> bool:
        if self.run_count >= self.settings.max_cloud_escalations_per_run:
            return False
        used = self.by_agent.get(role, 0)
        if used >= self.settings.max_cloud_escalations_per_agent:
            return False
        self.by_agent[role] = used + 1
        self.run_count += 1
        return True


class CloudRouter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def for_role(self, role: AgentRole) -> ModelSelection:
        """The role's primary cloud provider (chain position 0)."""
        return self.chain_for_role(role)[0]

    def chain_for_role(self, role: AgentRole) -> list[ModelSelection]:
        """The role's deterministic primary -> secondary cloud provider chain."""
        return [
            ModelSelection(role, profile, provider, model)
            for profile, (provider, model) in zip(_CLOUD_PROFILES, _CLOUD_CHAIN[role], strict=True)
        ]

    def enabled_for(self, provider: str) -> bool:
        key = self._settings.gemini_api_key if provider == "google" else self._settings.groq_api_key
        return self._settings.cloud_enabled and bool(key)


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


GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
_SAFE_BODY_CHARS = 500


class _ProviderHTTPError(Exception):
    """A non-2xx provider response captured from the same request, never retried for."""

    def __init__(self, status_code: int, safe_body: str) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.safe_body = safe_body


def extract_gemini_output_text(payload: dict[str, Any]) -> str:
    """Deterministically find the completed model output text in an Interactions response.

    Never guesses among ambiguous content; a missing model_output text step is
    a structured-output quality failure, not a silently accepted empty string.
    """
    for step in payload.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for item in step.get("content", []):
            if item.get("type") == "text" and "text" in item:
                return item["text"]
    raise ValueError("Gemini Interactions response has no model_output text step")


def _classify_attempt_exception(exc: Exception) -> tuple[ErrorCode, str]:
    if isinstance(exc, httpx.TimeoutException):
        return ErrorCode.AGENT_TIMEOUT, "provider request timed out"
    if isinstance(exc, _ProviderHTTPError):
        return ErrorCode.LLM_AVAILABILITY_ERROR, f"HTTP {exc.status_code}: {exc.safe_body}"
    if isinstance(exc, httpx.HTTPStatusError):
        return ErrorCode.LLM_AVAILABILITY_ERROR, f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.HTTPError):
        return ErrorCode.LLM_AVAILABILITY_ERROR, type(exc).__name__
    return ErrorCode.LLM_QUALITY_ERROR, f"{type(exc).__name__}: {exc}"


def is_cloud_eligible(error: ErrorCode) -> bool:
    return error in {
        ErrorCode.LLM_AVAILABILITY_ERROR,
        ErrorCode.LLM_QUALITY_ERROR,
        ErrorCode.SECURITY_CONFLICT,
        ErrorCode.AGENT_TIMEOUT,
        ErrorCode.NON_ACTIONABLE_REMEDIATION,
    }


class CloudModelRuntime:
    """Schema-constrained Gemini/Groq runtime walking a deterministic primary -> secondary
    cloud chain per role before the caller falls back to local Ollama."""

    def __init__(
        self, settings: Settings, *, client: httpx.Client | None = None,
        trace: Any | None = None,
    ) -> None:
        self.settings = settings
        self.router = CloudRouter(settings)
        self.budget = CloudBudget(settings)
        self.client = client
        self.trace = trace
        self.attempts: list[ModelExecutionInfo] = []
        self.outputs: dict[AgentRole, BaseModel] = {}

    def invoke_artifact(
        self,
        role: AgentRole,
        envelope: ContextEnvelope,
        candidate: BaseModel,
        *,
        mode: Literal["primary", "fallback"] = "fallback",
        fallback_reason: str | None = None,
        start_index: int = 0,
    ) -> tuple[BaseModel, ModelExecutionInfo]:
        """Walk the role's cloud chain from `start_index`, returning the first usable artifact.

        `start_index=1` lets a caller deliberately target only the secondary cloud
        provider (used for the Developer non-actionable-remediation escalation,
        which is not itself a provider error and so would not otherwise advance
        the chain). Each provider is attempted at most once per call.
        """
        chain = self.router.chain_for_role(role)[start_index:]
        if not chain:
            raise RuntimeError(
                f"{ErrorCode.LLM_AVAILABILITY_ERROR.value}: no further cloud provider configured"
            )

        schema_type, default_candidate, artifact_basis, preferred_paths = role_schema(role, candidate)
        output_schema = _governed_output_schema(schema_type)
        policy = _invocation_policy(role, schema_type)
        system_prompt, user_prompt = build_prompts(
            role, envelope, output_schema, default_candidate, policy=policy,
            preferred_paths=preferred_paths, artifact_basis=artifact_basis, trace=self.trace,
        )
        require_safe_cloud_context(system_prompt)
        require_safe_cloud_context(user_prompt)

        # A real attempt's failure is always more actionable than a later provider
        # being skipped (no credential, budget exhausted) — the final raise prefers
        # the last real attempt's classified error over a synthetic skip reason.
        last_error: str | None = None
        last_skip: str | None = None
        active_fallback_reason = fallback_reason
        for position, selection in enumerate(chain):
            is_free_primary = start_index == 0 and position == 0 and mode == "primary"
            attempt_mode = "primary" if is_free_primary else "fallback"
            if not self.router.enabled_for(selection.provider):
                last_skip = (
                    f"{ErrorCode.LLM_AVAILABILITY_ERROR.value}: "
                    f"{selection.provider} disabled or missing credential"
                )
                continue
            if not is_free_primary and not self.budget.consume(role):
                last_skip = "CLOUD_FALLBACK_UNAVAILABLE: escalation budget exhausted"
                continue

            started = time.perf_counter()
            owns_client = self.client is None
            client = self.client or httpx.Client(timeout=self.settings.llm_timeout_seconds)
            try:
                raw, usage = self._call_provider(
                    client, selection, system_prompt, user_prompt, output_schema,
                )
                parsed = schema_type.model_validate_json(raw)
                if not preserves_governed_facts(default_candidate, parsed, policy):
                    raise ValueError("governed artifact contradiction")
            except (
                httpx.HTTPError, KeyError, IndexError, TypeError, ValueError,
                ValidationError, _ProviderHTTPError,
            ) as exc:
                code, detail = _classify_attempt_exception(exc)
                error = (
                    f"CLOUD_FALLBACK_UNAVAILABLE: {detail}" if attempt_mode == "fallback"
                    else f"{code.value}: {detail}"
                )
                info = ModelExecutionInfo(
                    agent=role, provider=selection.provider, requested_model=selection.model,
                    actual_model=None, model_profile=selection.model_profile,
                    fallback_used=attempt_mode == "fallback",
                    fallback_reason=active_fallback_reason if attempt_mode == "fallback" else None,
                    degraded=True, latency_ms=int((time.perf_counter() - started) * 1000),
                    structured_output_success=False, error=error,
                )
                self.attempts.append(info)
                if self.trace is not None:
                    self.trace.record(
                        f"{role.value} cloud {attempt_mode} ({selection.provider})",
                        as_type="generation", metadata=info.model_dump(mode="json"),
                        level="ERROR", status_message=error,
                    )
                last_error = error
                active_fallback_reason = code.value
                continue
            finally:
                if owns_client:
                    client.close()
            artifact = merge_role_artifact(role, candidate, parsed)
            info = ModelExecutionInfo(
                agent=role, provider=selection.provider, requested_model=selection.model,
                actual_model=selection.model, model_profile=selection.model_profile,
                fallback_used=attempt_mode == "fallback",
                fallback_reason=active_fallback_reason if attempt_mode == "fallback" else None,
                latency_ms=int((time.perf_counter() - started) * 1000), usage=usage,
                structured_output_success=True,
            )
            self.attempts.append(info)
            self.outputs[role] = artifact
            if self.trace is not None:
                self.trace.record(
                    f"{role.value} cloud {attempt_mode} ({selection.provider})",
                    as_type="generation",
                    input={"system_prompt": system_prompt, "user_prompt": user_prompt},
                    output={"response": raw}, model=selection.model,
                    metadata=info.model_dump(mode="json"), usage_details=usage,
                )
            return artifact, info
        raise RuntimeError(
            last_error or last_skip
            or f"{ErrorCode.LLM_AVAILABILITY_ERROR.value}: no cloud provider available"
        )

    def _call_provider(
        self,
        client: httpx.Client,
        selection: ModelSelection,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """Issue exactly one provider HTTP call and return its raw structured-output text."""
        if selection.provider == "google":
            response = client.post(
                GEMINI_INTERACTIONS_URL,
                headers={
                    "x-goog-api-key": self.settings.gemini_api_key or "",
                    "Content-Type": "application/json",
                },
                json={
                    "model": selection.model,
                    "system_instruction": system_prompt,
                    "input": user_prompt,
                    "response_format": {
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": output_schema,
                    },
                    "store": False,
                },
            )
            if response.is_error:
                safe_body = redact_secrets(
                    response.text[:_SAFE_BODY_CHARS],
                    known_values=(self.settings.gemini_api_key or "",),
                )
                raise _ProviderHTTPError(response.status_code, safe_body)
            payload = response.json()
            return extract_gemini_output_text(payload), payload.get("usage")
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
        return payload["choices"][0]["message"]["content"], payload.get("usage")
