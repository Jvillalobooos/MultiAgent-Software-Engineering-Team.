"""Langfuse v4 adapter with an offline evidence-preserving mode."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engineering_team.guardrails.secrets import redact_secrets

_SENSITIVE_KEYS = {
    "api_key", "apikey", "secret", "secret_key", "password", "access_token",
    "authorization", "gemini_api_key", "groq_api_key", "langfuse_secret_key",
}


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in _SENSITIVE_KEYS else _safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value


@dataclass
class TraceSession:
    trace_id: str
    run_id: str
    live: bool
    root: Any | None = None
    client: Any | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = False
    live_error: str | None = None
    artifact_path: Path | None = None

    def record(
        self,
        name: str,
        *,
        as_type: str = "span",
        input: Any | None = None,
        output: Any | None = None,
        metadata: dict[str, Any] | None = None,
        level: str | None = None,
        status_message: str | None = None,
        model: str | None = None,
        usage_details: dict[str, int] | None = None,
    ) -> str:
        event = {
            "name": name,
            "type": as_type,
            "input": _safe(input),
            "output": _safe(output),
            "metadata": _safe(metadata or {}),
            "level": level,
            "status_message": _safe(status_message),
        }
        self.events.append(event)
        if self.root is None:
            return f"local-{len(self.events)}"
        kwargs: dict[str, Any] = {
            "name": name,
            "as_type": as_type,
            "input": event["input"],
            "output": event["output"],
            "metadata": event["metadata"],
        }
        if level is not None:
            kwargs["level"] = level
        if status_message is not None:
            kwargs["status_message"] = event["status_message"]
        if model is not None:
            kwargs["model"] = model
        if usage_details is not None:
            kwargs["usage_details"] = usage_details
        span = self.root.start_observation(**kwargs)
        span.end()
        return span.id

    def finish(self, final_report: Any) -> None:
        if self.finished:
            return
        safe_report = _safe(final_report)
        self.events.append({"name": "FinalReport", "type": "span", "output": safe_report})
        if self.root is not None:
            self.root.update(output=safe_report, metadata={"run_id": self.run_id})
            self.root.end()
            self.client.flush()
        if self.artifact_path is not None:
            self.artifact_path.parent.mkdir(parents=True, exist_ok=True)
            self.artifact_path.write_text(
                json.dumps({
                    "trace_id": self.trace_id, "run_id": self.run_id,
                    "live": self.live, "live_error": self.live_error,
                    "events": self.events,
                }, indent=2), encoding="utf-8",
            )
        self.finished = True


class LangfuseTracer:
    """Create exactly one correlated root observation for each workflow run."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        public_key: str | None = None,
        secret_key: str | None = None,
        base_url: str | None = None,
        offline_directory: str | Path | None = None,
    ) -> None:
        self._client = client
        self._auth_checked = False
        self._auth_error: str | None = None
        self._offline_directory = Path(offline_directory) if offline_directory else None
        if client is not None:
            return
        public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        base_url = (
            base_url
            or os.getenv("LANGFUSE_BASE_URL")
            or os.getenv("LANGFUSE_HOST")
        )
        if not (public_key and secret_key):
            return
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=public_key, secret_key=secret_key, base_url=base_url
        )

    @property
    def live(self) -> bool:
        return self._client is not None and self._auth_error is None

    def start_run(self, run_id: str, requirement: str) -> TraceSession:
        artifact_path = (
            self._offline_directory / f"{run_id}.json" if self._offline_directory else None
        )
        if self._client is not None and not self._auth_checked and hasattr(self._client, "auth_check"):
            self._auth_checked = True
            auth_errors: tuple[type[BaseException], ...] = (OSError, RuntimeError)
            auth_failure_errors: tuple[type[BaseException], ...] = ()
            try:
                from langfuse.api.commons.errors.unauthorized_error import UnauthorizedError
                from langfuse.api.core.api_error import ApiError

                auth_errors = (*auth_errors, ApiError)
                auth_failure_errors = (UnauthorizedError,)
            except ImportError:
                pass
            try:
                if not self._client.auth_check():
                    self._auth_error = "LANGFUSE_AUTH_FAILED"
            except auth_failure_errors:
                self._auth_error = "LANGFUSE_AUTH_FAILED"
            except auth_errors:
                self._auth_error = "LANGFUSE_UNAVAILABLE"
        if self._auth_error is not None:
            trace_id = uuid.uuid5(uuid.NAMESPACE_URL, f"engineering-team:{run_id}").hex
            return TraceSession(
                trace_id=trace_id, run_id=run_id, live=False, live_error=self._auth_error,
                artifact_path=artifact_path,
            )
        if self._client is None:
            trace_id = uuid.uuid5(uuid.NAMESPACE_URL, f"engineering-team:{run_id}").hex
            return TraceSession(
                trace_id=trace_id, run_id=run_id, live=False, artifact_path=artifact_path
            )
        trace_id = self._client.create_trace_id(seed=run_id)
        root = self._client.start_observation(
            trace_context={"trace_id": trace_id},
            name="Autonomous Engineering Team run",
            as_type="chain",
            input={"requirement": _safe(requirement)},
            metadata={"run_id": run_id},
        )
        return TraceSession(
            trace_id=trace_id, run_id=run_id, live=True, root=root, client=self._client,
            artifact_path=artifact_path,
        )


# Backwards-compatible local trace used by early unit tests.
@dataclass
class LocalTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    events: list[dict[str, str]] = field(default_factory=list)

    def record(self, name: str, detail: str) -> None:
        self.events.append({"name": name, "detail": redact_secrets(detail)})
