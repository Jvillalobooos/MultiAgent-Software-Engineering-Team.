"""CLOUD_FIRST default routing: primary/fallback order and budget isolation."""

import httpx
import pytest

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole, ErrorCode, ModelPriority
from engineering_team.contracts.models import ImplementationResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.cloud import CloudModelRuntime, is_cloud_eligible
from engineering_team.llm.priority import resolve_runtime_order
from engineering_team.models.context import build_context


class _Stub:
    def __init__(self):
        self.attempts = []
        self.calls = 0

    def invoke_artifact(self, role, envelope, candidate, *, mode="primary", fallback_reason=None):
        self.calls += 1
        return candidate, None


@pytest.mark.parametrize(
    ("priority", "expect_primary_cloud", "expect_fallback"),
    [
        (ModelPriority.CLOUD_FIRST, True, True),
        ("cloud_first", True, True),
        (ModelPriority.LOCAL_FIRST, False, True),
        (ModelPriority.CLOUD_ONLY, True, False),
        (ModelPriority.LOCAL_ONLY, False, False),
    ],
)
def test_resolve_runtime_order_matches_configured_strategy(
    priority, expect_primary_cloud, expect_fallback
) -> None:
    local, cloud = _Stub(), _Stub()

    order = resolve_runtime_order(priority, local, cloud)

    assert order.primary_is_cloud is expect_primary_cloud
    assert order.primary is (cloud if expect_primary_cloud else local)
    if expect_fallback:
        assert order.fallback is (local if expect_primary_cloud else cloud)
    else:
        assert order.fallback is None


def test_cloud_only_never_falls_back_to_local_even_when_local_is_provided() -> None:
    local, cloud = _Stub(), _Stub()

    order = resolve_runtime_order(ModelPriority.CLOUD_ONLY, local, cloud)

    assert order.fallback is None


def test_local_only_never_falls_back_to_cloud_even_when_cloud_is_provided() -> None:
    local, cloud = _Stub(), _Stub()

    order = resolve_runtime_order(ModelPriority.LOCAL_ONLY, local, cloud)

    assert order.fallback is None


def test_cloud_first_degrades_to_sole_local_primary_when_cloud_runtime_is_absent() -> None:
    local = _Stub()

    order = resolve_runtime_order(ModelPriority.CLOUD_FIRST, local, None)

    assert order.primary is local
    assert order.primary_is_cloud is False
    assert order.fallback is None


def test_local_first_degrades_to_sole_cloud_primary_when_local_runtime_is_absent() -> None:
    cloud = _Stub()

    order = resolve_runtime_order(ModelPriority.LOCAL_FIRST, None, cloud)

    assert order.primary is cloud
    assert order.fallback is None


def test_no_runtime_configured_yields_no_primary() -> None:
    order = resolve_runtime_order(ModelPriority.CLOUD_FIRST, None, None)

    assert order.primary is None
    assert order.fallback is None


def test_settings_default_model_priority_is_cloud_first() -> None:
    assert Settings(_env_file=None).model_priority is ModelPriority.CLOUD_FIRST


def test_non_actionable_remediation_is_cloud_eligible_for_escalation() -> None:
    assert is_cloud_eligible(ErrorCode.NON_ACTIONABLE_REMEDIATION)


def test_tool_mcp_rag_errors_remain_ineligible_for_provider_fallback() -> None:
    assert not is_cloud_eligible(ErrorCode.TOOL_ERROR)
    assert not is_cloud_eligible(ErrorCode.MCP_ERROR)
    assert not is_cloud_eligible(ErrorCode.RAG_ERROR)


def test_primary_cloud_call_does_not_consume_the_escalation_budget() -> None:
    state = EngineeringState(run_id="cloud-primary", requirement="safe code change")
    envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
    candidate = ImplementationResult(
        action_mode="PROPOSED", changed_files=[],
        diff="NO-OP: no inspected evidence", evidence=["mcp://repository/list_files"],
        validation_result="no-op: nothing inspected",
    )

    def handler(request):
        plan = {"mutations": [], "no_mutation_reason": "insufficient evidence", "blocker": None}
        return httpx.Response(200, json={
            "choices": [{"message": {"content": __import__("json").dumps(plan)}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })

    settings = Settings(_env_file=None, cloud_enabled=True, groq_api_key="configured")
    runtime = CloudModelRuntime(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    for _ in range(5):
        runtime.invoke_artifact(AgentRole.DEVELOPER, envelope, candidate, mode="primary")

    assert runtime.budget.run_count == 0
    assert runtime.budget.by_agent == {}


def test_fallback_cloud_call_still_consumes_the_bounded_escalation_budget() -> None:
    state = EngineeringState(run_id="cloud-fallback", requirement="safe code change")
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    from engineering_team.agents.product import ProductAgent

    candidate = ProductAgent().execute(envelope)

    def handler(request):
        return httpx.Response(200, json={
            "steps": [{
                "type": "model_output",
                "content": [{"type": "text", "text": candidate.model_dump_json()}],
            }],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    settings = Settings(_env_file=None, cloud_enabled=True, gemini_api_key="configured")
    runtime = CloudModelRuntime(
        settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )

    runtime.invoke_artifact(
        AgentRole.PRODUCT, envelope, candidate,
        mode="fallback", fallback_reason=ErrorCode.LLM_QUALITY_ERROR.value,
    )

    assert runtime.budget.run_count == 1
    assert runtime.budget.by_agent == {AgentRole.PRODUCT: 1}
