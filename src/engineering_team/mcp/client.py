"""Small synchronous boundary over official asynchronous MCP stdio sessions."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

from mcp import Client, StdioServerParameters

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ToolResult

T = TypeVar("T")


def _run_sync(awaitable: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, awaitable).result()


class _MCPStdioClient:
    transport = "stdio"

    def __init__(self, root: str | Path, kind: str, *, timeout_seconds: int = 60) -> None:
        self.root = Path(root).resolve()
        self.kind = kind
        self.timeout_seconds = timeout_seconds
        self.last_protocol_version: str | None = None
        self.last_server_name: str | None = None

    def _parameters(self) -> StdioServerParameters:
        return StdioServerParameters(
            command=sys.executable,
            args=[
                "-m", "engineering_team.mcp.server", "--kind", self.kind,
                "--root", str(self.root), "--timeout", str(self.timeout_seconds),
            ],
            cwd=self.root,
        )

    async def _discover(self) -> list[str]:
        async with Client(
            self._parameters(), read_timeout_seconds=float(self.timeout_seconds)
        ) as session:
            self._capture_session(session)
            result = await session.list_tools()
            return [tool.name for tool in result.tools]

    async def _invoke(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        async with Client(
            self._parameters(), read_timeout_seconds=float(self.timeout_seconds)
        ) as session:
            self._capture_session(session)
            result = await session.call_tool(name, arguments)
        payload = result.structured_content
        if not isinstance(payload, dict):
            text = next(
                (item.text for item in result.content if hasattr(item, "text")), "{}"
            )
            payload = json.loads(text)
        return ToolResult.model_validate(payload)

    def _capture_session(self, session: Client) -> None:
        self.last_protocol_version = str(session.protocol_version)
        if session.server_info is not None:
            self.last_server_name = session.server_info.name

    def list_tools(self) -> list[str]:
        return _run_sync(self._discover())

    def call_tool(self, name: str, role: AgentRole, **arguments: Any) -> ToolResult:
        try:
            return _run_sync(self._invoke(name, {"role": role.value, **arguments}))
        except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult(
                tool_name=name,
                allowed_role=role,
                status=ToolStatus.UNAVAILABLE,
                input_summary="safe",
                output_summary="",
                duration_ms=0,
                evidence_reference=f"mcp://{self.kind}/{name}",
                error=f"MCP_ERROR: {type(exc).__name__}",
            )


class MCPRepositoryClient(_MCPStdioClient):
    def __init__(self, root: str | Path, *, timeout_seconds: int = 60) -> None:
        super().__init__(root, "repository", timeout_seconds=timeout_seconds)

    def list_files(self, role: AgentRole) -> ToolResult:
        return self.call_tool("list_files", role)

    def read_file(self, role: AgentRole, relative: str) -> ToolResult:
        return self.call_tool("read_file", role, relative=relative)

    def search_code(self, role: AgentRole, query: str) -> ToolResult:
        return self.call_tool("search_code", role, query=query)

    def get_file_content(self, role: AgentRole, relative: str) -> ToolResult:
        return self.call_tool("get_file_content", role, relative=relative)

    def create_file(self, role: AgentRole, relative: str, content: str) -> ToolResult:
        return self.call_tool("create_file", role, relative=relative, content=content)

    def update_file(self, role: AgentRole, relative: str, content: str) -> ToolResult:
        return self.call_tool("update_file", role, relative=relative, content=content)

    def get_diff(self, role: AgentRole) -> ToolResult:
        return self.call_tool("get_diff", role)


class MCPQualityClient(_MCPStdioClient):
    def __init__(self, root: str | Path, *, timeout_seconds: int = 60) -> None:
        super().__init__(root, "quality", timeout_seconds=timeout_seconds)

    def run_tests(self, role: AgentRole, paths: list[str] | None = None) -> ToolResult:
        return self.call_tool("run_tests", role, paths=paths)

    def get_test_results(self, role: AgentRole) -> ToolResult:
        return self.call_tool("get_test_results", role)

    def run_build(self, role: AgentRole) -> ToolResult:
        return self.call_tool("run_build", role)

    def get_build_status(self, role: AgentRole) -> ToolResult:
        return self.call_tool("get_build_status", role)

    def run_linter(self, role: AgentRole) -> ToolResult:
        return self.call_tool("run_linter", role)

    def scan_dependencies(self, role: AgentRole) -> ToolResult:
        return self.call_tool("scan_dependencies", role)

    def run_security_scan(self, role: AgentRole) -> ToolResult:
        return self.call_tool("run_security_scan", role)

    def get_security_report(self, role: AgentRole) -> ToolResult:
        return self.call_tool("get_security_report", role)
