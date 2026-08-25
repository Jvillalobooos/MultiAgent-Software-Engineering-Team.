"""Ollama structured generation adapter."""

import time

import httpx

from engineering_team.contracts.models import ModelExecutionInfo

from .registry import ModelSelection


class OllamaAdapter:
    def __init__(self, base_url: str, *, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def generate(
        self, selection: ModelSelection, system_prompt: str, user_prompt: str, timeout: float = 60
    ) -> tuple[str, ModelExecutionInfo]:
        started = time.perf_counter()
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=timeout)
        try:
            response = await client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": selection.model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                    "format": "json",
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            code = (
                "AGENT_TIMEOUT"
                if isinstance(exc, httpx.TimeoutException)
                else "LLM_AVAILABILITY_ERROR"
            )
            raise RuntimeError(f"{code}: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        latency = int((time.perf_counter() - started) * 1000)
        usage = {key: payload[key] for key in ("prompt_eval_count", "eval_count") if key in payload}
        return str(payload.get("response", "")), ModelExecutionInfo(
            agent=selection.agent,
            provider="ollama",
            requested_model=selection.model,
            actual_model=payload.get("model", selection.model),
            model_profile=selection.model_profile,
            latency_ms=latency,
            usage=usage or None,
        )
