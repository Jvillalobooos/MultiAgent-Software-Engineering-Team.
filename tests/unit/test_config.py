from engineering_team.config import Settings


def test_settings_default_to_approved_local_model_policy() -> None:
    settings = Settings(_env_file=None)

    assert settings.fast_model == "qwen3.5:4b"
    assert settings.deep_model == "qwen3.5:9b"
    assert settings.coding_model == "qwen3.5:9b"
    assert settings.local_first is True
    assert settings.cloud_enabled is False
    assert settings.max_local_retries == 1
    assert settings.max_local_repairs == 1
    assert settings.max_cloud_escalations_per_agent == 1
    assert settings.max_cloud_escalations_per_run == 3
    assert settings.llm_timeout_seconds == 60


def test_settings_loads_canonical_langfuse_environment(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public-test-value")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret-test-value")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://canonical.example")

    settings = Settings(_env_file=None)

    assert settings.langfuse_public_key == "public-test-value"
    assert settings.langfuse_secret_key.get_secret_value() == "secret-test-value"
    assert settings.langfuse_base_url == "https://canonical.example"
    assert "secret-test-value" not in repr(settings)


def test_langfuse_base_url_precedes_legacy_host(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://canonical.example")
    monkeypatch.setenv("LANGFUSE_HOST", "https://legacy.example")

    settings = Settings(_env_file=None)

    assert settings.langfuse_base_url == "https://canonical.example"
