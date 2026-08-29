import pytest
import json

from engineering_team.contracts.enums import RouteTarget
from engineering_team.guardrails.routes import validate_route
from engineering_team.guardrails.secrets import redact_secrets, require_safe_cloud_context
from engineering_team.guardrails.validation import require_explicit_destructive_authorization


def test_secret_redactor_removes_known_secret_values() -> None:
    assert "secret-value" not in redact_secrets("token=secret-value", {"secret-value"})


def test_cloud_context_rejects_env_content() -> None:
    with pytest.raises(ValueError, match="sensitive"):
        require_safe_cloud_context({"file": ".env", "content": "KEY=value"})


@pytest.mark.parametrize("key", ["mistral_api_key", "open_router_api_key", "openrouter_api_key"])
def test_cloud_context_rejects_new_provider_credentials(key):
    with pytest.raises(ValueError, match="sensitive"):
        require_safe_cloud_context({key: "credential-value"})


@pytest.mark.parametrize("source", [
    "def login(password: str):\n    return verify(password)\n",
    "def contraseña(password: str):\n    return verify(password)\n",
    "class Login:\n    password: str = Field(min_length=1, max_length=256)\n",
])
def test_cloud_guard_accepts_type_declarations_without_credentials(source):
    require_safe_cloud_context(source)
    require_safe_cloud_context("ContextEnvelope: " + json.dumps({"content": source}))
    require_safe_cloud_context("Repository data:\n```python\n" + source + "\n```")


@pytest.mark.parametrize("source", [
    'password = "real-value"',
    'def login(password: str = "real-value"):\n    pass',
    'class Login:\n    password: str = "real-value"',
    'class Login:\n    password: str = Field(default="real-value")',
    'class Login:\n    password: str = Field(\n        # secret=real-value\n        min_length=1\n    )',
    'class Login:\n    password: (\n        # secret=real-value\n        str\n    )',
    'def login(password: str):\n    # secret=real-value\n    pass',
    'def contraseña(password: str):\n    secret="real-value"\n    return password',
])
def test_cloud_guard_still_rejects_secrets_in_typed_python(source):
    with pytest.raises(ValueError, match="sensitive"):
        require_safe_cloud_context(source)
    with pytest.raises(ValueError, match="sensitive"):
        require_safe_cloud_context("ContextEnvelope: " + json.dumps({"content": source}))
    with pytest.raises(ValueError, match="sensitive"):
        require_safe_cloud_context("Repository data:\n```python\n" + source + "\n```")


def test_route_validator_rejects_disallowed_target() -> None:
    with pytest.raises(ValueError):
        validate_route(RouteTarget.ARCHITECTURE, {RouteTarget.DEVELOPER})


def test_destructive_operations_require_explicit_authorization() -> None:
    with pytest.raises(PermissionError):
        require_explicit_destructive_authorization(False)


def test_documented_password_parameter_is_not_treated_as_a_secret() -> None:
    """A Google-style Args entry documents an argument; it carries no value.

    The agents write these routinely, and blocking them stopped legitimate runs on
    a docstring line that contained no credential at all.
    """
    require_safe_cloud_context(
        'def restablecer(token, nueva_password):\n'
        '    """Restablece la contraseña.\n\n'
        '    Args:\n'
        '        nueva_password: Nueva contraseña para el usuario.\n'
        '    """\n'
    )


@pytest.mark.parametrize(
    "docstring_value",
    [
        "password: hunter2",
        "api_key: aB3xQ9tZ7LmW2pR4vN8sK1",
        "password: la clave es aB3xQ9tZ7LmW2pR4vN8",
    ],
)
def test_a_real_credential_inside_a_docstring_is_still_blocked(docstring_value: str) -> None:
    """The prose exemption must not become a way to smuggle a value out.

    A bare token has no whitespace, and a credential-shaped run is rejected even when
    it is surrounded by prose.
    """
    with pytest.raises(ValueError, match="sensitive content"):
        require_safe_cloud_context(f'def f():\n    """Doc.\n\n    Args:\n        {docstring_value}\n    """\n')
