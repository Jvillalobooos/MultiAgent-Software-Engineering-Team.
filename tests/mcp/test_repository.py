from pathlib import Path

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.mcp.repository import RepositoryMCP
from engineering_team.workspace.isolation import create_run_copy


def test_repository_mcp_reads_and_writes_only_inside_run_workspace(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("hello", encoding="utf-8")
    mcp = RepositoryMCP(tmp_path)

    assert "file.txt" in mcp.list_files(AgentRole.DEVELOPER).output_summary
    assert mcp.read_file(AgentRole.ARCHITECTURE, "file.txt").status is ToolStatus.SUCCESS
    assert mcp.create_file(AgentRole.DEVELOPER, "new.txt", "safe").status is ToolStatus.SUCCESS


def test_repository_mcp_denies_path_traversal_and_architecture_writes(tmp_path: Path) -> None:
    mcp = RepositoryMCP(tmp_path)
    assert mcp.read_file(AgentRole.DEVELOPER, "../outside.txt").status is ToolStatus.DENIED
    assert mcp.create_file(AgentRole.ARCHITECTURE, "x.txt", "x").status is ToolStatus.DENIED


def test_each_run_uses_an_isolated_source_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.py").write_text("safe = True", encoding="utf-8")

    run = create_run_copy("run-123", source, tmp_path / "runs")
    RepositoryMCP(run).update_file(AgentRole.DEVELOPER, "app.py", "safe = False")

    assert (source / "app.py").read_text(encoding="utf-8") == "safe = True"
    assert (run / "app.py").read_text(encoding="utf-8") == "safe = False"


def test_search_code_never_reads_secret_paths_but_keeps_allowed_matches(tmp_path: Path) -> None:
    sentinel = "FICTIONAL_REPOSITORY_SENTINEL_77"
    (tmp_path / ".env").write_text(sentinel, encoding="utf-8")
    (tmp_path / ".env.audit").write_text(sentinel, encoding="utf-8")
    (tmp_path / "allowed.py").write_text(sentinel, encoding="utf-8")
    mcp = RepositoryMCP(tmp_path)

    result = mcp.search_code(AgentRole.DEVELOPER, sentinel)

    assert result.status is ToolStatus.SUCCESS
    assert result.output_summary.splitlines() == ["allowed.py"]
    assert sentinel not in result.output_summary
