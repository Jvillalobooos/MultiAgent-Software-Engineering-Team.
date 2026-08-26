import json
from pathlib import Path

from engineering_team.capabilities import detect_project_capabilities
from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.mcp.quality import QualityMCP


def test_quality_mcp_preserves_failed_test_result(tmp_path: Path) -> None:
    (tmp_path / "test_failure.py").write_text(
        "def test_fails():\n    assert False\n", encoding="utf-8"
    )
    result = QualityMCP(tmp_path).run_tests(AgentRole.TESTING, ["test_failure.py"])

    assert result.status is ToolStatus.FAIL
    assert "failed" in result.output_summary.lower()


def test_quality_mcp_is_deny_by_default_for_every_operation(tmp_path: Path) -> None:
    mcp = QualityMCP(tmp_path)
    operations = {
        "run_tests": ({AgentRole.TESTING}, lambda role: mcp.run_tests(role, [])),
        "get_test_results": ({AgentRole.TESTING}, mcp.get_test_results),
        "run_build": ({AgentRole.DEVELOPER, AgentRole.TESTING}, mcp.run_build),
        "get_build_status": (
            {AgentRole.DEVELOPER, AgentRole.TESTING}, mcp.get_build_status
        ),
        "run_linter": ({AgentRole.DEVELOPER, AgentRole.TESTING}, mcp.run_linter),
        "scan_dependencies": ({AgentRole.SECURITY}, mcp.scan_dependencies),
        "run_security_scan": ({AgentRole.SECURITY}, mcp.run_security_scan),
        "get_security_report": ({AgentRole.SECURITY}, mcp.get_security_report),
    }
    for name, (allowed, operation) in operations.items():
        for role in AgentRole:
            if role not in allowed:
                result = operation(role)
                assert result.status is ToolStatus.DENIED
                assert result.tool_name == name


def test_denied_quality_operation_never_starts_subprocess(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("subprocess must not execute for a denied role")

    monkeypatch.setattr("engineering_team.mcp.quality.subprocess.run", forbidden)
    result = QualityMCP(tmp_path).scan_dependencies(AgentRole.PRODUCT)
    assert result.status is ToolStatus.DENIED


def test_quality_getter_preserves_last_real_result(tmp_path: Path) -> None:
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    mcp = QualityMCP(tmp_path)
    executed = mcp.run_tests(AgentRole.TESTING, ["test_ok.py"])
    retrieved = mcp.get_test_results(AgentRole.TESTING)

    assert executed.status is ToolStatus.SUCCESS
    assert retrieved.status is ToolStatus.SUCCESS
    assert "passed" in retrieved.output_summary.lower()


def test_quality_uses_declared_node_test_command_and_profile_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    project = tmp_path / "web"
    project.mkdir()
    (project / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )
    profile = detect_project_capabilities(tmp_path)
    captured = {}

    class Completed:
        returncode = 0
        stdout = "tests passed"
        stderr = ""

    def execute(args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return Completed()

    monkeypatch.setattr("engineering_team.mcp.quality.subprocess.run", execute)

    result = QualityMCP(tmp_path).run_tests(
        AgentRole.TESTING,
        profile_fingerprint=profile.fingerprint,
    )

    assert result.status is ToolStatus.SUCCESS
    assert captured["args"] == ["npm", "test"]
    assert Path(captured["kwargs"]["cwd"]) == project
    assert captured["kwargs"]["shell"] is False


def test_quality_routes_dotnet_build_without_executing_python(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "Demo.sln").write_text("solution", encoding="utf-8")
    profile = detect_project_capabilities(tmp_path)
    calls = []

    class Completed:
        returncode = 0
        stdout = "build passed"
        stderr = ""

    monkeypatch.setattr(
        "engineering_team.mcp.quality.subprocess.run",
        lambda args, **kwargs: calls.append(args) or Completed(),
    )

    result = QualityMCP(tmp_path).run_build(
        AgentRole.DEVELOPER,
        profile_fingerprint=profile.fingerprint,
    )

    assert result.status is ToolStatus.SUCCESS
    assert calls == [["dotnet", "build"]]


def test_quality_rejects_profile_mismatch_without_subprocess(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("subprocess must not run for a mismatched profile")

    monkeypatch.setattr("engineering_team.mcp.quality.subprocess.run", forbidden)

    result = QualityMCP(tmp_path).run_tests(
        AgentRole.TESTING,
        profile_fingerprint="0" * 64,
    )

    assert result.status is ToolStatus.DENIED
    assert "fingerprint mismatch" in (result.error or "")
