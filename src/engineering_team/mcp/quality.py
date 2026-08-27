import subprocess
import sys
import time
import tomllib
from pathlib import Path

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ToolResult


class QualityMCP:
    def __init__(self, root: str | Path, *, timeout_seconds: int = 60) -> None:
        self.root = Path(root).resolve()
        self.timeout_seconds = timeout_seconds
        self._last: dict[str, ToolResult] = {}
        self._dependencies_prepared = False

    def _prepare_project_dependencies(self, role: AgentRole) -> ToolResult | None:
        """Install declared runtime dependencies once in the test interpreter."""
        if self._dependencies_prepared:
            return None
        self._dependencies_prepared = True
        pyproject = self.root / "pyproject.toml"
        if not pyproject.is_file():
            return None
        try:
            metadata = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return None
        dependencies = metadata.get("project", {}).get("dependencies", [])
        if not dependencies:
            return None
        result = self._run(
            role,
            "install_dependencies",
            [
                sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                "--no-input", ".",
            ],
            {AgentRole.TESTING},
        )
        if result.status is ToolStatus.SUCCESS:
            return None
        return result.model_copy(update={"tool_name": "run_tests"})

    def _static(
        self, role: AgentRole, tool: str, allowed: set[AgentRole], output: str
    ) -> ToolResult:
        if role not in allowed:
            return ToolResult(
                tool_name=tool, allowed_role=role, status=ToolStatus.DENIED,
                input_summary="denied", output_summary="", duration_ms=0,
                error="role denied",
            )
        return ToolResult(
            tool_name=tool, allowed_role=role, status=ToolStatus.SUCCESS,
            input_summary="safe", output_summary=output, duration_ms=0,
        )

    def _run(
        self, role: AgentRole, tool: str, args: list[str], allowed: set[AgentRole]
    ) -> ToolResult:
        if role not in allowed:
            return ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=ToolStatus.DENIED,
                input_summary="denied",
                output_summary="",
                duration_ms=0,
                error="role denied",
            )
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                args, cwd=self.root, capture_output=True, text=True,
                timeout=self.timeout_seconds, check=False
            )
            output = (proc.stdout + proc.stderr)[-4000:]
            status = ToolStatus.SUCCESS if proc.returncode == 0 else ToolStatus.FAIL
            result = ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=status,
                input_summary="safe",
                output_summary=output,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            self._last[tool] = result
            return result
        except (OSError, subprocess.TimeoutExpired) as exc:
            result = ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=ToolStatus.UNAVAILABLE,
                input_summary="safe",
                output_summary="",
                duration_ms=int((time.perf_counter() - started) * 1000),
                error=str(exc),
            )
            self._last[tool] = result
            return result

    def _get_last(
        self, role: AgentRole, getter: str, source: str, allowed: set[AgentRole]
    ) -> ToolResult:
        if role not in allowed:
            return self._static(role, getter, allowed, "")
        previous = self._last.get(source)
        return ToolResult(
            tool_name=getter, allowed_role=role,
            status=previous.status if previous else ToolStatus.UNAVAILABLE,
            input_summary="safe",
            output_summary=previous.output_summary if previous else f"no {source} result",
            duration_ms=0,
            error=previous.error if previous else f"{source} has not executed",
        )

    def run_tests(self, role: AgentRole, paths: list[str] | None = None) -> ToolResult:
        if role is not AgentRole.TESTING:
            return self._run(
                role, "run_tests", [sys.executable, "-m", "pytest", *(paths or [])],
                {AgentRole.TESTING},
            )
        prepared = self._prepare_project_dependencies(role)
        if prepared is not None:
            return prepared
        return self._run(
            role, "run_tests", [sys.executable, "-m", "pytest", *(paths or [])], {AgentRole.TESTING}
        )

    def get_test_results(self, role: AgentRole) -> ToolResult:
        return self._get_last(
            role, "get_test_results", "run_tests", {AgentRole.TESTING}
        )

    def run_build(self, role: AgentRole) -> ToolResult:
        return self._run(
            role,
            "run_build",
            [sys.executable, "-m", "compileall", "."],
            {AgentRole.DEVELOPER, AgentRole.TESTING},
        )

    def get_build_status(self, role: AgentRole) -> ToolResult:
        return self._get_last(
            role, "get_build_status", "run_build",
            {AgentRole.DEVELOPER, AgentRole.TESTING},
        )

    def run_linter(self, role: AgentRole) -> ToolResult:
        return self._run(
            role,
            "run_linter",
            [sys.executable, "-m", "ruff", "check", "."],
            {AgentRole.DEVELOPER, AgentRole.TESTING},
        )

    def scan_dependencies(self, role: AgentRole) -> ToolResult:
        return self._run(
            role, "scan_dependencies", [sys.executable, "-m", "pip", "check"],
            {AgentRole.SECURITY},
        )

    def run_security_scan(self, role: AgentRole) -> ToolResult:
        target = (
            "app" if (self.root / "app").is_dir()
            else "sample_app/app" if (self.root / "sample_app" / "app").is_dir()
            else "."
        )
        return self._run(
            role, "run_security_scan",
            [
                sys.executable, "-m", "ruff", "check", target, "--select", "S",
                "--extend-exclude", "tests,test,test_*.py,*_test.py",
            ],
            {AgentRole.SECURITY},
        )

    def get_security_report(self, role: AgentRole) -> ToolResult:
        return self._get_last(
            role, "get_security_report", "run_security_scan", {AgentRole.SECURITY},
        )
