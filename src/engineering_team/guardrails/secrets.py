"""Secret redaction and outbound payload validation."""

import re
from collections.abc import Iterable
from typing import Any

_SENSITIVE_KEYS = {
    "api_key", "apikey", "secret", "secret_key", "access_token", "password",
    "gemini_api_key", "groq_api_key", "langfuse_secret_key",
}


def redact_secrets(value: str, known_values: Iterable[str] = ()) -> str:
    redacted = value
    for secret in known_values:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return re.sub(
        r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,]+", r"\1=[REDACTED]", redacted
    )


def require_safe_cloud_context(value: Any) -> None:
    if isinstance(value, dict):
        if any(str(key).lower() in _SENSITIVE_KEYS for key in value):
            raise ValueError("sensitive content is not allowed in cloud context")
        for item in value.values():
            require_safe_cloud_context(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            require_safe_cloud_context(item)
        return
    text = str(value)
    if ".env" in text.lower() or re.search(
        r"(?i)(api[_-]?key|access[_-]?token|password|secret)\s*[=:]\s*[^\s,]+", text
    ):
        raise ValueError("sensitive content is not allowed in cloud context")
