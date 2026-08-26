import pytest

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ToolResult
from engineering_team.graph.stategraph import build_engineering_graph
from engineering_team.mcp.repository import RepositoryMCP


class RecordingQuality:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def _success(self, tool: str, role: AgentRole, fingerprint: str | None) -> ToolResult:
        self.calls.append((tool, fingerprint))
        return ToolResult(
            tool_name=tool,
            allowed_role=role,
            status=ToolStatus.SUCCESS,
            input_summary="safe",
            output_summary="native validation passed",
            duration_ms=1,
        )

    def run_tests(self, role, paths=None, profile_fingerprint=None):
        return self._success("run_tests", role, profile_fingerprint)

    def run_build(self, role, profile_fingerprint=None):
        return self._success("run_build", role, profile_fingerprint)


@pytest.mark.parametrize(
    ("ecosystem", "fixture", "expected_tools"),
    [
        (
            "python",
            {"pyproject.toml": "[project]\nname = 'sample'\n"},
            ["run_tests"],
        ),
        (
            "node",
            {"package.json": '{"scripts":{"test":"vitest run","build":"tsc"}}\n'},
            ["run_build", "run_tests"],
        ),
        (
            "dotnet",
            {"Sample.csproj": "<Project Sdk=\"Microsoft.NET.Sdk\"/>\n"},
            ["run_build", "run_tests"],
        ),
    ],
)
def test_supported_ecosystem_workflow_routes_all_required_native_validations(
    tmp_path, ecosystem, fixture, expected_tools
) -> None:
    for relative, content in fixture.items():
        (tmp_path / relative).write_text(content, encoding="utf-8")
    quality = RecordingQuality()

    result = build_engineering_graph(
        repository_mcp=RepositoryMCP(tmp_path),
        quality_mcp=quality,
    ).invoke({"run_id": f"cross-{ecosystem}", "requirement": "validate project"})

    profile = result["project_capabilities"]
    assert profile.ecosystem.value == ecosystem
    assert [tool for tool, _ in quality.calls] == expected_tools
    assert all(fingerprint == profile.fingerprint for _, fingerprint in quality.calls)
    assert result["final_status"] == "APPROVED"
