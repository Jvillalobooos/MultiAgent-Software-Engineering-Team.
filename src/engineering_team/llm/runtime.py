"""Synchronous local-model runtime used by LangGraph nodes."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.models import ModelExecutionInfo, StrictModel
from engineering_team.llm.router import ModelRouter
from engineering_team.models.context import ContextEnvelope


class StructuredAgentObservation(StrictModel):
    acknowledged: bool


class LocalModelRuntime:
    """Route and invoke Ollama once per agent with schema-constrained JSON."""

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        trace: Any | None = None,
    ) -> None:
        self.settings = settings
        self.router = ModelRouter(settings)
        self.client = client
        self.trace = trace
        self.outputs: dict[AgentRole, BaseModel] = {}
        self.attempts: list[ModelExecutionInfo] = []

    def invoke(self, role: AgentRole, envelope: ContextEnvelope) -> ModelExecutionInfo:
        """Compatibility health invocation; production graph uses invoke_artifact."""
        _, info = self._invoke_schema(role, envelope, StructuredAgentObservation, {"acknowledged": True})
        return info

    def invoke_artifact(
        self, role: AgentRole, envelope: ContextEnvelope, candidate: BaseModel
    ) -> tuple[BaseModel, ModelExecutionInfo]:
        """Return the role-specific, schema-validated artifact produced by Ollama."""
        return self._invoke_schema(role, envelope, type(candidate), candidate.model_dump(mode="json"))

    def _invoke_schema(
        self, role: AgentRole, envelope: ContextEnvelope,
        schema_type: type[BaseModel], candidate: dict[str, Any],
    ) -> tuple[BaseModel, ModelExecutionInfo]:
        selection = self.router.local_for(role)
        output_schema = _governed_output_schema(schema_type)
        system_prompt, user_prompt = self._prompts(
            role, envelope, output_schema, candidate
        )
        availability_attempt = 0
        repair_attempt = 0
        while True:
            started = time.perf_counter()
            owns_client = self.client is None
            client = self.client or httpx.Client(timeout=self.settings.llm_timeout_seconds)
            payload: dict[str, Any] = {}
            try:
                response = client.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/generate",
                    json={
                        "model": selection.model,
                        "system": system_prompt,
                        "prompt": user_prompt,
                        "stream": False,
                        "think": False,
                        "format": output_schema,
                        "options": {"temperature": 0, "num_predict": 2048},
                    },
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                latency = int((time.perf_counter() - started) * 1000)
                info = ModelExecutionInfo(
                    agent=role, provider="ollama", requested_model=selection.model,
                    actual_model=payload.get("model"), model_profile=selection.model_profile,
                    degraded=True, latency_ms=latency, structured_output_success=False,
                    error=f"LLM_AVAILABILITY_ERROR: {type(exc).__name__}",
                )
                self.attempts.append(info)
                self._record(role, system_prompt, user_prompt, payload.get("response"), info,
                             retry=availability_attempt, repair=repair_attempt)
                if availability_attempt < self.settings.max_local_retries:
                    availability_attempt += 1
                    continue
                raise RuntimeError(info.error) from exc
            finally:
                if owns_client:
                    client.close()
            latency = int((time.perf_counter() - started) * 1000)
            raw = str(payload.get("response", ""))
            usage = {
                key: payload[key]
                for key in ("prompt_eval_count", "eval_count")
                if key in payload
            }
            try:
                parsed = schema_type.model_validate_json(raw)
            except ValidationError as exc:
                info = ModelExecutionInfo(
                    agent=role, provider="ollama", requested_model=selection.model,
                    actual_model=payload.get("model", selection.model),
                    model_profile=selection.model_profile, degraded=True, latency_ms=latency,
                    usage=usage or None, structured_output_success=False,
                    error="LLM_QUALITY_ERROR: invalid structured response",
                )
                self.attempts.append(info)
                self._record(role, system_prompt, user_prompt, raw, info,
                             retry=availability_attempt, repair=repair_attempt)
                if repair_attempt < self.settings.max_local_repairs:
                    repair_attempt += 1
                    user_prompt += "\nRepair the previous response. Return only valid schema JSON."
                    continue
                raise RuntimeError(info.error) from exc
            if not _preserves_governed_facts(candidate, parsed):
                info = ModelExecutionInfo(
                    agent=role, provider="ollama", requested_model=selection.model,
                    actual_model=payload.get("model", selection.model),
                    model_profile=selection.model_profile, degraded=True,
                    latency_ms=latency, usage=usage or None,
                    structured_output_success=False,
                    error="LLM_QUALITY_ERROR: governed artifact contradiction",
                )
                self.attempts.append(info)
                self._record(
                    role, system_prompt, user_prompt, raw, info,
                    retry=availability_attempt, repair=repair_attempt,
                )
                if repair_attempt < self.settings.max_local_repairs:
                    repair_attempt += 1
                    user_prompt = (
                        "Repair governed artifact contradiction. Return only this candidate "
                        "artifact as JSON, preserving every key and value exactly:\n"
                        f"{json.dumps(candidate, ensure_ascii=False)}"
                    )
                    continue
                raise RuntimeError(info.error)
            info = ModelExecutionInfo(
                agent=role, provider="ollama", requested_model=selection.model,
                actual_model=payload.get("model", selection.model),
                model_profile=selection.model_profile, latency_ms=latency, usage=usage or None,
                structured_output_success=True,
            )
            self.outputs[role] = parsed
            self.attempts.append(info)
            self._record(role, system_prompt, user_prompt, raw, info,
                         retry=availability_attempt, repair=repair_attempt)
            return parsed, info

    def _prompts(
        self, role: AgentRole, envelope: ContextEnvelope,
        output_schema: dict[str, Any] | type[BaseModel], candidate: dict[str, Any],
    ) -> tuple[str, str]:
        if isinstance(output_schema, type) and issubclass(output_schema, BaseModel):
            output_schema = _governed_output_schema(output_schema)
        directory = Path(__file__).parents[1] / "prompts" / role.value.lower()
        system = (directory / "system.md").read_text(encoding="utf-8").strip()
        system += (
            "\nReturn only one JSON object matching the supplied role-specific schema. "
            "Preserve all governed facts, findings, statuses, and evidence from the "
            "candidate artifact. Do not add prose or fields."
        )
        projection = {
            key: (
                str(value)[:300]
                if key in {"run_id", "requirement"}
                else ("present" if value is not None else "absent")
            )
            for key, value in envelope.state_projection.items()
        }
        context = {
            "agent": envelope.agent.value,
            "current_task": envelope.current_task,
            "state_projection": projection,
            "rag_evidence": [
                {
                    "source": item.source, "section": item.section, "chunk_id": item.chunk_id,
                    "score": item.score,
                }
                for item in envelope.rag_evidence
            ],
            "tool_results": [
                {"tool": item.tool_name, "status": item.status.value}
                for item in envelope.tool_results
            ],
            "remediation_feedback": envelope.remediation_feedback,
        }
        user = (
            f"Task: {envelope.current_task}\n"
            f"ContextEnvelope: {json.dumps(context, ensure_ascii=False)}\n"
            f"Output schema: {json.dumps(output_schema)}\n"
            f"Candidate artifact: {json.dumps(candidate, ensure_ascii=False)}\n"
            "Copy every candidate key and value exactly; do not omit schema-optional keys."
        )
        return system, user

    def _record(
        self, role: AgentRole, system: str, user: str, response: Any,
        info: ModelExecutionInfo, *, retry: int, repair: int,
    ) -> None:
        if self.trace is None:
            return
        self.trace.record(
            f"{role.value} model", as_type="generation",
            input={"system_prompt": system, "user_prompt": user},
            output={"response": response}, model=info.actual_model or info.requested_model,
            usage_details=info.usage,
            metadata={
                **info.model_dump(mode="json"), "retry": retry, "repair": repair,
            },
            level="ERROR" if info.error else "DEFAULT", status_message=info.error,
        )


def _contains_all(actual: list[Any], governed: list[Any]) -> bool:
    return all(item in actual for item in governed)


def _governed_output_schema(schema_type: type[BaseModel]) -> dict[str, Any]:
    """Require every governed candidate key in Ollama's structured output grammar."""
    schema = schema_type.model_json_schema()
    schema["required"] = list(schema.get("properties", {}))
    return schema


def _same_items(actual: list[Any], governed: list[Any]) -> bool:
    return _contains_all(actual, governed) and _contains_all(governed, actual)


def _preserves_governed_facts(candidate: dict[str, Any], parsed: BaseModel) -> bool:
    """Prevent schema-valid model output from weakening deterministic evidence."""
    actual = parsed.model_dump(mode="json")
    model_name = type(parsed).__name__
    if model_name == "ImplementationResult":
        return actual == candidate
    guarded_lists: dict[str, tuple[str, ...]] = {
        "ProductSpecification": (
            "business_rules", "constraints", "acceptance_criteria", "nfrs",
        ),
        "ArchitectureProposal": ("risks", "evidence_references"),
        "ImplementationResult": ("evidence",),
        "SecurityReview": ("findings", "sources"),
        "TestResult": ("failures", "evidence_references", "actual_results"),
        "ReviewerDecision": ("problems", "evidence_references"),
    }
    guarded_values: dict[str, tuple[str, ...]] = {
        "ProductSpecification": ("source_requirement",),
        "ImplementationResult": ("security_surface_changed",),
        "SecurityReview": ("status", "highest_severity", "requires_hitl"),
        "TestResult": ("status",),
        "ReviewerDecision": ("status", "remediation_category", "return_to"),
    }
    if any(actual.get(key) != candidate.get(key) for key in guarded_values.get(model_name, ())):
        return False
    if any(
        not _contains_all(actual.get(key, []), candidate.get(key, []))
        for key in guarded_lists.get(model_name, ())
    ):
        return False
    exact_evidence_lists: dict[str, tuple[str, ...]] = {
        "ArchitectureProposal": ("evidence_references",),
        "SecurityReview": ("sources",),
        "TestResult": ("evidence_references",),
        "ReviewerDecision": ("evidence_references",),
    }
    if any(
        not _same_items(actual.get(key, []), candidate.get(key, []))
        for key in exact_evidence_lists.get(model_name, ())
    ):
        return False
    if model_name == "SecurityReview":
        expected_checklist = candidate.get("checklist", {})
        actual_checklist = actual.get("checklist", {})
        if any(
            expected == "FAIL" and actual_checklist.get(key) != "FAIL"
            for key, expected in expected_checklist.items()
        ):
            return False
    return True
