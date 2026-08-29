import pytest
import json

from engineering_team.agents.product import ProductAgent
from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.enums import ToolStatus
from engineering_team.contracts.models import ToolResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.llm.prompting import build_role_prompts, governed_output_schema
from engineering_team.models.context import build_context


@pytest.mark.parametrize("role", list(AgentRole))
def test_consumed_system_prompt_declares_role_boundaries_evidence_and_authority(role) -> None:
    state = EngineeringState(run_id="prompt", requirement="safe bounded change")
    candidate = ProductAgent().execute(build_context(AgentRole.PRODUCT, state, "Product"))
    envelope = build_context(role, state, role.value)

    system, _ = build_role_prompts(
        role, envelope, type(candidate), candidate.model_dump(mode="json")
    )

    assert f"ROLE: {role.value}" in system
    assert "RESPONSIBILITY:" in system
    assert "BOUNDARIES:" in system
    assert "EVIDENCE TO PRESERVE:" in system
    assert "OUTPUT CONTRACT:" in system
    assert "NO ROUTING / NO MODEL SELECTION:" in system


def test_prompt_does_not_present_a_truncated_requirement_as_the_canonical_one():
    requirement = "Implement a small banking operation. " * 12 + "Require authenticated ownership."
    state = EngineeringState(run_id="prompt", requirement=requirement)
    envelope = build_context(AgentRole.PRODUCT, state, "Product")
    candidate = ProductAgent().execute(envelope)
    _, user = build_role_prompts(AgentRole.PRODUCT, envelope, type(candidate), candidate.model_dump(mode="json"))
    context_line = next(line for line in user.splitlines() if line.startswith("ContextEnvelope: "))
    context = json.loads(context_line.removeprefix("ContextEnvelope: "))
    assert context["state_projection"]["requirement"] == requirement


def test_developer_reads_source_with_real_line_breaks_not_nested_json_escapes():
    source = 'def login(password: str):\n    return verify(password)\n'
    state = EngineeringState(run_id="prompt", requirement="Edit app.py", tool_results=[ToolResult(
        tool_name="read_file", allowed_role=AgentRole.DEVELOPER, status=ToolStatus.SUCCESS,
        input_summary="path=app.py", output_summary=source, duration_ms=0,
    )])
    envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
    _, user = build_role_prompts(AgentRole.DEVELOPER, envelope, {}, {"action_mode": "APPLIED"})
    assert source in user
    assert "```python" in user
    from engineering_team.guardrails.secrets import require_safe_cloud_context
    require_safe_cloud_context(user)


def test_remediation_prompt_uses_latest_read_of_each_file_and_preserves_audit():
    tools = [ToolResult(tool_name="read_file", allowed_role=AgentRole.DEVELOPER,
                        status=ToolStatus.SUCCESS, input_summary="app.py",
                        output_summary=source, duration_ms=0)
             for source in ["obsolete_value = 1\n", "current_value = 2\n"]]
    state = EngineeringState(run_id="prompt", requirement="Edit app.py", tool_results=tools)
    envelope = build_context(AgentRole.DEVELOPER, state, "Developer")
    _, user = build_role_prompts(AgentRole.DEVELOPER, envelope, {}, {"action_mode": "APPLIED"})
    assert "obsolete_value" not in user
    assert user.count("current_value = 2") == 1
    assert envelope.tool_results == tools


def test_apply_schema_constrains_paths_and_facts_but_leaves_code_to_the_model():
    from engineering_team.contracts.models import ImplementationResult
    candidate = ImplementationResult(action_mode="APPLIED", changed_files=["app.py"],
        diff="planned", evidence=["mcp://read/app.py"], validation_result="pending",
        security_surface_changed=True, file_contents={})
    schema = governed_output_schema(ImplementationResult, candidate.model_dump(mode="json"))
    assert schema["properties"]["changed_files"]["const"] == ["app.py"]
    assert schema["properties"]["evidence"]["const"] == candidate.evidence
    contents = schema["properties"]["file_contents"]
    assert contents["required"] == ["app.py"]
    assert contents["additionalProperties"] is False
    assert contents["properties"]["app.py"] == {"type": "string"}
