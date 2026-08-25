import pytest

from engineering_team.contracts.enums import RouteTarget
from engineering_team.guardrails.routes import validate_route
from engineering_team.guardrails.secrets import redact_secrets, require_safe_cloud_context
from engineering_team.guardrails.validation import require_explicit_destructive_authorization


def test_secret_redactor_removes_known_secret_values() -> None:
    assert "secret-value" not in redact_secrets("token=secret-value", {"secret-value"})


def test_cloud_context_rejects_env_content() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        require_safe_cloud_context({"file": ".env", "content": "KEY=value"})


def test_route_validator_rejects_disallowed_target() -> None:
    with pytest.raises(ValueError):
        validate_route(RouteTarget.ARCHITECTURE, {RouteTarget.DEVELOPER})


def test_destructive_operations_require_explicit_authorization() -> None:
    with pytest.raises(PermissionError):
        require_explicit_destructive_authorization(False)
