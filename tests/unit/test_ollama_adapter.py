import asyncio

import httpx
import pytest

from engineering_team.contracts.enums import AgentRole
from engineering_team.llm.ollama import OllamaAdapter
from engineering_team.llm.registry import ModelSelection


def test_ollama_adapter_returns_structured_execution_info() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"response": '{"objective":"ok"}', "model": "qwen3.5:9b", "eval_count": 7}
        )
    )
    adapter = OllamaAdapter("http://unused", client=httpx.AsyncClient(transport=transport))
    selection = ModelSelection(AgentRole.PRODUCT, "DEEP_MODEL", "ollama", "qwen3.5:9b")

    result, info = asyncio.run(adapter.generate(selection, "system", "user"))

    assert result == '{"objective":"ok"}'
    assert info.actual_model == "qwen3.5:9b"
    assert info.usage == {"eval_count": 7}


def test_ollama_adapter_classifies_transport_failure() -> None:
    transport = httpx.MockTransport(
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("down"))
    )
    adapter = OllamaAdapter("http://unused", client=httpx.AsyncClient(transport=transport))
    selection = ModelSelection(AgentRole.PRODUCT, "DEEP_MODEL", "ollama", "qwen3.5:9b")

    with pytest.raises(RuntimeError, match="LLM_AVAILABILITY_ERROR"):
        asyncio.run(adapter.generate(selection, "system", "user"))
