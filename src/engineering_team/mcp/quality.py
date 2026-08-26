import subprocess
import time
from pathlib import Path

from engineering_team.capabilities import command_for, detect_project_capabilities
from engineering_team.contracts.enums import AgentRole, ProjectCapabilityStatus, ToolStatus
from engineering_team.contracts.models import ToolResult


class QualityMCP:
    def __init__(self, root: str | Path, *, timeout_seconds: int = 60) -> None:
        self.root = Path(root).resolve()
        self.timeout_seconds = timeout_seconds
        self._last: dict[str, ToolResult] = {}

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
        self,
        role: AgentRole,
        tool: str,
        args: list[str],
        allowed: set[AgentRole],
        *,
        cwd: Path | None = None,
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
                args,
                cwd=cwd or self.root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
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

    def _run_capability(
        self,
        role: AgentRole,
        tool: str,
        capability: str,
        allowed: set[AgentRole],
        *,
        paths: list[str] | None = None,
        profile_fingerprint: str | None = None,
    ) -> ToolResult:
        if role not in allowed:
            return self._static(role, tool, allowed, "")
        profile = detect_project_capabilities(self.root)
        if profile_fingerprint is not None and profile.fingerprint != profile_fingerprint:
            return ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=ToolStatus.DENIED,
                input_summary="profile=invalid",
                output_summary="",
                duration_ms=0,
                error="project capability fingerprint mismatch",
            )
        if profile.status is not ProjectCapabilityStatus.SUPPORTED:
            return ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=ToolStatus.UNAVAILABLE,
                input_summary="profile=unsupported",
                output_summary="",
                duration_ms=0,
                error="; ".join(profile.missing_capabilities),
            )
        try:
            args = command_for(profile, capability, paths)
        except ValueError as exc:
            return ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=ToolStatus.DENIED,
                input_summary="paths=invalid",
                output_summary="",
                duration_ms=0,
                error=str(exc),
            )
        if args is None:
            return ToolResult(
                tool_name=tool,
                allowed_role=role,
                status=ToolStatus.UNAVAILABLE,
                input_summary=f"capability={capability}",
                output_summary="",
                duration_ms=0,
                error=f"project does not declare {capability}",
            )
        command = profile.commands[capability]
        return self._run(
            role,
            tool,
            args,
            allowed,
            cwd=(self.root / command.cwd).resolve(),
        )

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

    def run_tests(
        self,
        role: AgentRole,
        paths: list[str] | None = None,
        profile_fingerprint: str | None = None,
    ) -> ToolResult:
        return self._run_capability(
            role,
            "run_tests",
            "test",
            {AgentRole.TESTING},
            paths=paths,
            profile_fingerprint=profile_fingerprint,
        )

    def get_test_results(self, role: AgentRole) -> ToolResult:
        return self._get_last(
            role, "get_test_results", "run_tests", {AgentRole.TESTING}
        )

    def run_build(
        self, role: AgentRole, profile_fingerprint: str | None = None
    ) -> ToolResult:
        return self._run_capability(
            role,
            "run_build",
            "build",
            {AgentRole.DEVELOPER, AgentRole.TESTING},
            profile_fingerprint=profile_fingerprint,
        )

    def get_build_status(self, role: AgentRole) -> ToolResult:
        return self._get_last(
            role, "get_build_status", "run_build",
            {AgentRole.DEVELOPER, AgentRole.TESTING},
        )

    def run_linter(
        self, role: AgentRole, profile_fingerprint: str | None = None
    ) -> ToolResult:
        return self._run_capability(
            role,
            "run_linter",
            "lint",
            {AgentRole.DEVELOPER, AgentRole.TESTING},
            profile_fingerprint=profile_fingerprint,
        )

    def scan_dependencies(
        self, role: AgentRole, profile_fingerprint: str | None = None
    ) -> ToolResult:
        return self._run_capability(
            role,
            "scan_dependencies",
            "dependency_check",
            {AgentRole.SECURITY},
            profile_fingerprint=profile_fingerprint,
        )

    def run_security_scan(
        self, role: AgentRole, profile_fingerprint: str | None = None
    ) -> ToolResult:
        return self._run_capability(
            role,
            "run_security_scan",
            "security_scan",
            {AgentRole.SECURITY},
            profile_fingerprint=profile_fingerprint,
        )

    def get_security_report(self, role: AgentRole) -> ToolResult:
        return self._get_last(
            role, "get_security_report", "run_security_scan", {AgentRole.SECURITY},
        )
