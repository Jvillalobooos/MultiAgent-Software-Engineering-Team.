from engineering_team.observability.langfuse import LangfuseTracer


class FakeSpan:
    def __init__(self, name, trace_id="trace-1", **kwargs):
        self.name = name
        self.trace_id = trace_id
        self.id = f"span-{name}"
        self.kwargs = kwargs
        self.children = []
        self.ended = False

    def start_observation(self, **kwargs):
        span = FakeSpan(**kwargs, trace_id=self.trace_id)
        self.children.append(span)
        return span

    def update(self, **kwargs):
        self.kwargs.update(kwargs)
        return self

    def end(self):
        self.ended = True
        return self


class FakeLangfuse:
    def __init__(self):
        self.roots = []
        self.flushed = False

    def create_trace_id(self, *, seed):
        return f"trace-{seed}"

    def start_observation(self, **kwargs):
        span = FakeSpan(**kwargs, trace_id=kwargs["trace_context"]["trace_id"])
        self.roots.append(span)
        return span

    def flush(self):
        self.flushed = True


def test_langfuse_adapter_creates_one_root_and_complete_child_telemetry() -> None:
    client = FakeLangfuse()
    tracer = LangfuseTracer(client=client)
    trace = tracer.start_run("run-123", "password recovery")

    trace.record(
        "Product",
        as_type="agent",
        input={"system_prompt": "role", "user_prompt": "password=leak"},
        output={"response": "ok"},
        metadata={
            "requested_model": "qwen3.5:9b",
            "actual_model": "qwen3.5:9b",
            "model_profile": "DEEP_MODEL",
            "provider": "ollama",
            "latency_ms": 10,
            "usage": {"input_tokens": 2},
            "structured_output_success": True,
            "fallback_used": False,
            "error": None,
        },
    )
    trace.record("RAG retrieval", as_type="retriever", metadata={"source": "security.md"})
    trace.record("MCP call", as_type="tool", metadata={"tool_result": "SUCCESS"})
    trace.finish({"final_status": "APPROVED"})

    assert trace.trace_id == "trace-run-123"
    assert len(client.roots) == 1
    root = client.roots[0]
    assert [span.name for span in root.children] == ["Product", "RAG retrieval", "MCP call"]
    assert "leak" not in str(root.children[0].kwargs)
    assert root.ended is True
    assert client.flushed is True


def test_langfuse_without_credentials_keeps_local_correlated_trace(monkeypatch) -> None:
    for key in (
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL",
        "LANGFUSE_HOST",
    ):
        monkeypatch.delenv(key, raising=False)

    trace = LangfuseTracer().start_run("offline-run", "requirement")
    trace.record("retry", metadata={"iteration": 1})
    trace.finish({"final_status": "HUMAN_REVIEW_REQUIRED"})

    assert trace.live is False
    assert trace.trace_id
    assert [event["name"] for event in trace.events] == ["retry", "FinalReport"]


def test_langfuse_invalid_credentials_do_not_claim_live_export() -> None:
    class InvalidClient(FakeLangfuse):
        def auth_check(self):
            return False

    trace = LangfuseTracer(client=InvalidClient()).start_run("invalid", "requirement")

    assert trace.live is False
    assert trace.live_error == "LANGFUSE_AUTH_FAILED"


def test_adapter_uses_canonical_base_url_and_exports_live(monkeypatch) -> None:
    captured = {}
    client = FakeLangfuse()
    client.auth_check = lambda: True

    def build_client(**kwargs):
        captured.update(kwargs)
        return client

    monkeypatch.setattr("langfuse.Langfuse", build_client)
    tracer = LangfuseTracer(
        public_key="public-test-value",
        secret_key="secret-test-value",
        base_url="https://canonical.example",
    )
    trace = tracer.start_run("canonical", "configuration check")
    trace.finish({"status": "PASS"})

    assert captured == {
        "public_key": "public-test-value",
        "secret_key": "secret-test-value",
        "base_url": "https://canonical.example",
    }
    assert trace.live is True
    assert client.flushed is True
