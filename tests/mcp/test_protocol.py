from pathlib import Path

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient


def test_repository_tools_execute_through_real_stdio_mcp_session(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("enabled = True\n", encoding="utf-8")
    client = MCPRepositoryClient(tmp_path)

    discovery = client.list_tools()
    listed = client.list_files(AgentRole.DEVELOPER)
    read = client.read_file(AgentRole.ARCHITECTURE, "app.py")

    assert client.transport == "stdio"
    assert {"list_files", "read_file", "search_code", "get_file_content",
            "create_file", "update_file", "get_diff"} <= set(discovery)
    assert listed.status is ToolStatus.SUCCESS
    assert "app.py" in listed.output_summary
    assert read.status is ToolStatus.SUCCESS
    assert "enabled = True" in read.output_summary


def test_repository_protocol_preserves_permissions_and_traversal_guard(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=never-read\n", encoding="utf-8")
    client = MCPRepositoryClient(tmp_path)

    listed = client.list_files(AgentRole.DEVELOPER)
    secret = client.read_file(AgentRole.DEVELOPER, ".env")
    traversal = client.read_file(AgentRole.DEVELOPER, "../outside.txt")
    denied_write = client.create_file(AgentRole.ARCHITECTURE, "x.py", "unsafe")

    assert traversal.status is ToolStatus.DENIED
    assert denied_write.status is ToolStatus.DENIED
    assert not (tmp_path / "x.py").exists()
    assert ".env" not in listed.output_summary
    assert secret.status is ToolStatus.DENIED
    assert "never-read" not in secret.output_summary


def test_quality_run_tests_executes_through_real_stdio_mcp_session(tmp_path: Path) -> None:
    (tmp_path / "test_failure.py").write_text(
        "def test_failure():\n    assert False\n", encoding="utf-8"
    )
    client = MCPQualityClient(tmp_path)

    discovery = client.list_tools()
    result = client.run_tests(AgentRole.TESTING, ["test_failure.py"])

    assert client.transport == "stdio"
    assert {"run_tests", "get_test_results", "run_build", "get_build_status",
            "run_linter", "scan_dependencies", "run_security_scan",
            "get_security_report"} <= set(discovery)
    assert result.status is ToolStatus.FAIL
    assert "failed" in result.output_summary.lower()
