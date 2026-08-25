from pathlib import Path

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.mcp.client import MCPQualityClient, MCPRepositoryClient


def test_repository_tools_execute_through_real_stdio_mcp_session(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("enabled = True\n", encoding="utf-8")
    with MCPRepositoryClient(tmp_path) as client:
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
    with MCPRepositoryClient(tmp_path) as client:
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


def test_repository_search_code_excludes_secret_paths_over_real_protocol(tmp_path: Path) -> None:
    sentinel = "FICTIONAL_AUDIT_SENTINEL_42"
    (tmp_path / ".env").write_text(f"TOKEN={sentinel}\n", encoding="utf-8")
    (tmp_path / ".env.audit").write_text(f"TOKEN={sentinel}\n", encoding="utf-8")
    (tmp_path / "allowed.py").write_text(f"marker = '{sentinel}'\n", encoding="utf-8")

    with MCPRepositoryClient(tmp_path) as client:
        result = client.search_code(AgentRole.DEVELOPER, sentinel)

    assert result.status is ToolStatus.SUCCESS
    assert result.output_summary.splitlines() == ["allowed.py"]
    assert ".env" not in result.output_summary
    assert sentinel not in result.output_summary


def test_quality_run_tests_executes_through_real_stdio_mcp_session(tmp_path: Path) -> None:
    (tmp_path / "test_failure.py").write_text(
        "def test_failure():\n    assert False\n", encoding="utf-8"
    )
    with MCPQualityClient(tmp_path) as client:
        discovery = client.list_tools()
        result = client.run_tests(AgentRole.TESTING, ["test_failure.py"])

        assert client.transport == "stdio"

    assert {"run_tests", "get_test_results", "run_build", "get_build_status",
            "run_linter", "scan_dependencies", "run_security_scan",
            "get_security_report"} <= set(discovery)
    assert result.status is ToolStatus.FAIL
    assert "failed" in result.output_summary.lower()


def test_quality_getters_preserve_results_in_one_real_stdio_session(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")

    with MCPQualityClient(tmp_path) as client:
        executed_tests = client.run_tests(AgentRole.TESTING, ["test_ok.py"])
        fetched_tests = client.get_test_results(AgentRole.TESTING)
        executed_build = client.run_build(AgentRole.DEVELOPER)
        fetched_build = client.get_build_status(AgentRole.DEVELOPER)
        executed_scan = client.run_security_scan(AgentRole.SECURITY)
        fetched_scan = client.get_security_report(AgentRole.SECURITY)

    assert fetched_tests.status is executed_tests.status
    assert fetched_tests.output_summary == executed_tests.output_summary
    assert fetched_build.status is executed_build.status
    assert fetched_build.output_summary == executed_build.output_summary
    assert fetched_scan.status is executed_scan.status
    assert fetched_scan.output_summary == executed_scan.output_summary


def test_repository_get_diff_reports_real_updates_and_creates_over_protocol(tmp_path: Path) -> None:
    (tmp_path / "existing.py").write_text("value = 'old'\n", encoding="utf-8")

    with MCPRepositoryClient(tmp_path) as client:
        no_changes = client.get_diff(AgentRole.DEVELOPER)
        updated = client.update_file(
            AgentRole.DEVELOPER, "existing.py", "value = 'new'\n"
        )
        created = client.create_file(
            AgentRole.DEVELOPER, "created.py", "created = True\n"
        )
        diff = client.get_diff(AgentRole.DEVELOPER)

    assert no_changes.status is ToolStatus.SUCCESS
    assert no_changes.output_summary == ""
    assert updated.status is ToolStatus.SUCCESS
    assert created.status is ToolStatus.SUCCESS
    assert "-value = 'old'" in diff.output_summary
    assert "+value = 'new'" in diff.output_summary
    assert "+++ b/existing.py" in diff.output_summary
    assert "+++ b/created.py" in diff.output_summary
    assert "+created = True" in diff.output_summary
