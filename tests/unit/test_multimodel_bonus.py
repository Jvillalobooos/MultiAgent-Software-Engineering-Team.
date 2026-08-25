from engineering_team.observability.evaluation import _multi_model_bonus_pass


def test_bonus_uses_final_valid_local_execution_after_a_retry() -> None:
    expected = [
        ("Product", "qwen3.5:9b"), ("Architecture", "qwen3.5:4b"),
        ("Developer", "qwen3.5:9b"), ("Security", "qwen3.5:9b"),
        ("Testing", "qwen3.5:4b"), ("Reviewer", "qwen3.5:9b"),
    ]
    failed_retry = {
        "agent": "Developer", "provider": "ollama", "actual_model": "qwen3.5:9b",
        "structured_output_success": False, "error": "invalid output",
    }
    successful = [
        {
            "agent": role, "provider": "ollama", "actual_model": model,
            "structured_output_success": True, "error": None,
        }
        for role, model in expected
    ]

    assert _multi_model_bonus_pass(
        [failed_retry, *successful], expected, "qwen3.5:4b", "qwen3.5:9b"
    )
