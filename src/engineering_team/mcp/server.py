"""Official MCP SDK server bootstrap for bounded repository and quality tools."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.models import ToolResult
from engineering_team.mcp.quality import QualityMCP
from engineering_team.mcp.repository import RepositoryMCP


def _wire_result(server_name: str, operation: Callable[..., ToolResult], *args: Any) -> dict[str, Any]:
    result = operation(*args).model_copy(
        update={"evidence_reference": f"mcp://{server_name}/{operation.__name__}"}
    )
    return result.model_dump(mode="json")


def build_repository_server(root: str | Path) -> MCPServer:
    backend = RepositoryMCP(root)
    server = MCPServer(name="engineering-team-repository", log_level="ERROR")

    @server.tool()
    def list_files(role: str) -> dict[str, Any]:
        return _wire_result("repository", backend.list_files, AgentRole(role))

    @server.tool()
    def read_file(role: str, relative: str) -> dict[str, Any]:
        result = backend.read_file(AgentRole(role), relative).model_copy(update={
            "input_summary": f"path={relative}",
            "evidence_reference": "mcp://repository/read_file",
        })
        return result.model_dump(mode="json")

    @server.tool()
    def search_code(role: str, query: str) -> dict[str, Any]:
        result = backend.search_code(AgentRole(role), query).model_copy(update={
            "input_summary": "query=bounded",
            "evidence_reference": "mcp://repository/search_code",
        })
        return result.model_dump(mode="json")

    @server.tool()
    def get_file_content(role: str, relative: str) -> dict[str, Any]:
        result = backend.get_file_content(AgentRole(role), relative).model_copy(
            update={
                "input_summary": f"path={relative}",
                "evidence_reference": "mcp://repository/get_file_content",
            }
        )
        return result.model_dump(mode="json")

    @server.tool()
    def create_file(role: str, relative: str, content: str) -> dict[str, Any]:
        return _wire_result(
            "repository", backend.create_file, AgentRole(role), relative, content
        )

    @server.tool()
    def update_file(role: str, relative: str, content: str) -> dict[str, Any]:
        return _wire_result(
            "repository", backend.update_file, AgentRole(role), relative, content
        )

    @server.tool()
    def get_diff(role: str) -> dict[str, Any]:
        return _wire_result("repository", backend.get_diff, AgentRole(role))

    return server


def build_quality_server(root: str | Path, timeout_seconds: int = 60) -> MCPServer:
    backend = QualityMCP(root, timeout_seconds=timeout_seconds)
    server = MCPServer(name="engineering-team-quality", log_level="ERROR")

    @server.tool()
    def run_tests(role: str, paths: list[str] | None = None) -> dict[str, Any]:
        return _wire_result("quality", backend.run_tests, AgentRole(role), paths)

    @server.tool()
    def get_test_results(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.get_test_results, AgentRole(role))

    @server.tool()
    def run_build(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.run_build, AgentRole(role))

    @server.tool()
    def get_build_status(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.get_build_status, AgentRole(role))

    @server.tool()
    def run_linter(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.run_linter, AgentRole(role))

    @server.tool()
    def scan_dependencies(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.scan_dependencies, AgentRole(role))

    @server.tool()
    def run_security_scan(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.run_security_scan, AgentRole(role))

    @server.tool()
    def get_security_report(role: str) -> dict[str, Any]:
        return _wire_result("quality", backend.get_security_report, AgentRole(role))

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("repository", "quality"), required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    server = (
        build_repository_server(args.root)
        if args.kind == "repository"
        else build_quality_server(args.root, args.timeout)
    )
    server.run("stdio")


if __name__ == "__main__":
    main()
