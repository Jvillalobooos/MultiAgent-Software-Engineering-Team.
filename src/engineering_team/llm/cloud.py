"""Bounded cloud contingency routing; not normal model selection."""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
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

# Every provider but Google speaks the OpenAI chat-completions shape, so one code
# path serves them all; only the endpoint and the credential differ.
_OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "groq_api_key"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "mistral_api_key"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", "open_router_api_key"),
}

# Selected from observed role-level results, not catalogue size. See the model
# evaluation in banca-demo-support. Primaries span three providers and the first
# fallback always crosses providers. Google quotas can be model scoped: a 3.6 quota
# failure must not disable a working 3.5 fallback. Testing/Reviewer are deterministic.
_ROLE_CHAINS: dict[AgentRole, tuple[tuple[str, str], ...]] = {
    AgentRole.PRODUCT: (
        ("groq", "openai/gpt-oss-120b"),
        ("mistral", "mistral-small-latest"),
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("google", "gemini-3.5-flash"),
    ),
    AgentRole.ARCHITECTURE: (
        ("mistral", "mistral-medium-latest"),
        ("groq", "openai/gpt-oss-120b"),
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("google", "gemini-3.5-flash"),
    ),
    # Codestral and Small passed the isolated recovery acceptance test. Medium was
    # 0/10 on Developer in the historical runs, although reliable on Architecture.
    # Groq can reject full source payloads with HTTP 413, but does so quickly.
    # Gemini is last after the new 90s timeout; do not spend its wait before Small.
    AgentRole.DEVELOPER: (
        ("mistral", "codestral-latest"),
        ("groq", "openai/gpt-oss-120b"),
        ("mistral", "mistral-small-latest"),
        ("google", "gemini-3.5-flash"),
    ),
    AgentRole.SECURITY: (
        ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
        ("groq", "openai/gpt-oss-120b"),
        ("mistral", "mistral-small-latest"),
        ("google", "gemini-3.5-flash"),
    ),
}

# SambaNova was removed, not demoted: all seven models in its catalogue answer
# HTTP 402 ("a payment method is required") on this account, so it has no free tier to
# fall back to and every attempt would be a wasted round trip.

# Probed with the real request shape and deliberately absent from every chain:
#   openai/gpt-oss-120b:free       HTTP 404, no longer offered free by OpenRouter
#   nvidia/nemotron-3-ultra:free   answers 200 with malformed JSON, twice out of two
#   thinkingmachines/inkling:free  HTTP 403, paid plans only
#   z-ai/glm-5.2:free              HTTP 429 from the upstream provider
#   google/gemma-4-*:free          HTTP 429 from the upstream provider
#   ministral-3b-latest            returns valid JSON that omits required fields
#   mistral-large-latest           read timeout
#   gemini-2.5-flash               HTTP 404, no longer available to new users
#   gemini-3.1-flash-lite          failed schema validation on 40% of its responses

_CLOUD_MAP = {
    role: (chain[0][0], chain[0][1]) for role, chain in _ROLE_CHAINS.items()
}
_CLOUD_MAP[AgentRole.TESTING] = ("groq", "openai/gpt-oss-20b")
_CLOUD_MAP[AgentRole.REVIEWER] = ("groq", "openai/gpt-oss-120b")


class _GovernedContradiction(ValueError):
    def __init__(self, candidate: dict[str, Any], actual: BaseModel) -> None:
        values = actual.model_dump(mode="json")
        self.fields = sorted(key for key, value in candidate.items() if values.get(key) != value)
        super().__init__("governed artifact contradiction")


class _IncompleteOutput(ValueError):
    pass


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

    def _override(self, role: AgentRole) -> tuple[tuple[str, str], ...]:
        """Per-role override from settings, as "provider:model,provider:model"."""
        raw = getattr(self._settings, f"cloud_chain_{role.value.lower()}", "") or ""
        parsed = []
        for item in raw.split(","):
            item = item.strip()
            if not item or ":" not in item:
                continue
            provider, _, model = item.partition(":")
            parsed.append((provider.strip(), model.strip()))
        return tuple(parsed)

    def selection_chain(self, role: AgentRole) -> tuple[ModelSelection, ...]:
        """Every cloud model to try for a role, in order, before giving up.

        Cross providers early to limit correlated outages, but keep validated models
        only. Rate limits may be scoped to a model, account, or upstream provider.
        """
        pairs = self._override(role) or _ROLE_CHAINS.get(role)
        if not pairs:
            provider, model = _CLOUD_MAP[role]
            alternate = (
                "openai/gpt-oss-120b"
                if model == "openai/gpt-oss-20b"
                else "openai/gpt-oss-20b"
            )
            return (
                ModelSelection(role, "CLOUD_FALLBACK", provider, model),
                ModelSelection(role, "CLOUD_FALLBACK", provider, alternate),
            )
        seen, chain = set(), []
        for provider, model in pairs:
            if (provider, model) in seen:
                continue
            seen.add((provider, model))
            chain.append(ModelSelection(role, "CLOUD_FALLBACK", provider, model))
        return tuple(chain)

    def enabled_for(self, selection: ModelSelection) -> bool:
        if selection.provider == "google":
            key = self._settings.gemini_api_key
        else:
            entry = _OPENAI_COMPATIBLE.get(selection.provider)
            key = getattr(self._settings, entry[1], None) if entry else None
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
    """Validated runtime for Gemini, Groq, Mistral and OpenRouter.

    Usable either as the *fallback* runtime (bounded by ``CloudBudget``, the
    historical role) or as the *primary* runtime for a cloud-first
    configuration (``primary=True``), in which case the per-agent/per-run
    escalation caps are disabled since four model-invoking agents per run is the expected
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
        self._unavailable_until: dict[tuple[str, str], float] = {}

    def invoke_artifact(
        self,
        role: AgentRole,
        envelope: ContextEnvelope,
        candidate: BaseModel,
        *,
        fallback_reason: str = "CLOUD_FIRST",
        _attempt: int = 0,
        _deadline: float | None = None,
    ) -> tuple[BaseModel, ModelExecutionInfo]:
        chain = self.router.selection_chain(role)
        deadline = _deadline if _deadline is not None else time.monotonic() + self.settings.cloud_role_timeout_seconds
        # The budget bounds *escalations*, not the retries within one escalation: every
        # model in the chain is one attempt at the same escalation, so it is consumed
        # once, on entry, and never again as the chain is walked. It must be charged
        # before the credential skip below, otherwise an unconfigured first provider
        # would advance the cursor past this check and escalate for free.
        if _attempt == 0 and not self.budget.consume(role):
            raise RuntimeError("CLOUD_FALLBACK_UNAVAILABLE: disabled, missing credential, or budget")
        # Skip entries whose provider has no usable credential rather than aborting the
        # whole chain on the first unconfigured one.
        while _attempt < len(chain) and (
            not self.router.enabled_for(chain[_attempt])
            or self._unavailable_until.get((chain[_attempt].provider, "*"), 0) > time.monotonic()
            or self._unavailable_until.get((chain[_attempt].provider, chain[_attempt].model), 0) > time.monotonic()
        ):
            _attempt += 1
        if _attempt >= len(chain):
            raise RuntimeError("CLOUD_FALLBACK_UNAVAILABLE: disabled, missing credential, or budget")
        selection = chain[_attempt]
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("CLOUD_FALLBACK_UNAVAILABLE: role deadline exceeded")
        request_timeout = min(self.settings.llm_timeout_seconds, remaining)
        candidate_dict = candidate.model_dump(mode="json")
        output_schema = governed_output_schema(type(candidate), candidate_dict)
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
        client = self.client or httpx.Client(timeout=request_timeout)
        started = time.perf_counter()
        try:
            if selection.provider == "google":
                response = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{selection.model}:generateContent",
                    headers={"x-goog-api-key": self.settings.gemini_api_key or ""},
                    timeout=request_timeout,
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
                endpoint, credential = _OPENAI_COMPATIBLE[selection.provider]
                schema_mode = (selection.provider == "mistral" or
                    (selection.provider == "openrouter" and selection.model != "minimax/minimax-m3:free"))
                response_format = ({"type": "json_schema", "json_schema": {
                    "name": type(candidate).__name__, "schema": output_schema, "strict": True,
                }} if schema_mode else {"type": "json_object"})
                provider_options = ({"provider": {
                    "require_parameters": True, "max_price": {"prompt": 0, "completion": 0},
                }, "max_tokens": 16000 if role is AgentRole.DEVELOPER else 4096,
                    "reasoning": {"effort": "low", "exclude": True},
                } if selection.provider == "openrouter" else {})
                response = client.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {getattr(self.settings, credential, None) or ''}"
                    },
                    timeout=request_timeout,
                    json={
                        "model": selection.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0,
                        "response_format": response_format,
                        **provider_options,
                    },
                )
                response.raise_for_status()
                payload = response.json()
                if payload["choices"][0].get("finish_reason") == "length":
                    raise _IncompleteOutput("model output reached its token limit")
                raw = payload["choices"][0]["message"]["content"]
                usage = payload.get("usage")
            artifact = type(candidate).model_validate_json(raw)
            if not _preserves_governed_facts(candidate.model_dump(mode="json"), artifact):
                raise _GovernedContradiction(candidate_dict, artifact)
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            category, retryable = _http_category(status)
            if status in {401, 402, 403, 429, 503}:
                cooldown = 30.0
                hint = exc.response.headers.get("Retry-After")
                if hint:
                    try:
                        cooldown = max(0, float(hint))
                    except ValueError:
                        try:
                            cooldown = max(0, (parsedate_to_datetime(hint) - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                if status in {401, 402, 403}:
                    cooldown = float("inf")
                # A quota/capacity failure can be model-specific (observed with
                # Gemini 3.6 vs 3.5). Only credential/payment errors disable the
                # whole provider; preserve healthy alternate models.
                key = (selection.provider, "*" if status in {401, 402, 403} else selection.model)
                self._unavailable_until[key] = time.monotonic() + cooldown
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
            if _attempt + 1 < len(chain):
                return self.invoke_artifact(
                    role, envelope, candidate, fallback_reason=fallback_reason,
                    _attempt=_attempt + 1,
                    _deadline=deadline,
                )
            raise RuntimeError(error) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            contradiction = isinstance(exc, _GovernedContradiction)
            detail = (
                f"governed fields differ: {', '.join(exc.fields)}"
                if contradiction else
                "schema validation: " + ", ".join(sorted({e["type"] for e in exc.errors(include_input=False)}))
                if isinstance(exc, ValidationError) else type(exc).__name__
            )
            error = f"CLOUD_FALLBACK_UNAVAILABLE: {detail}"
            info = ModelExecutionInfo(
                agent=role, provider=selection.provider, requested_model=selection.model,
                actual_model=None, model_profile=selection.model_profile,
                fallback_used=True, fallback_reason=fallback_reason, degraded=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
                structured_output_success=False, error=error,
                error_category=("governed_contradiction" if contradiction else
                                "incomplete_output" if isinstance(exc, _IncompleteOutput) else
                                "timeout" if isinstance(exc, httpx.TimeoutException) else
                                "schema_validation" if isinstance(exc, ValidationError) else "invalid_response"),
                retryable=True,
            )
            self.attempts.append(info)
            if self.trace is not None:
                self.trace.record(
                    f"{role.value} cloud {'primary' if self.primary else 'fallback'}",
                    as_type="generation",
                    metadata=info.model_dump(mode="json"), level="ERROR",
                    status_message=error,
                )
            if _attempt + 1 < len(chain):
                return self.invoke_artifact(
                    role, envelope, candidate, fallback_reason=fallback_reason,
                    _attempt=_attempt + 1,
                    _deadline=deadline,
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
