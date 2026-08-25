from pathlib import Path

from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ToolResult

_READ_ROLES = {AgentRole.ARCHITECTURE, AgentRole.DEVELOPER}
_WRITE_ROLES = {AgentRole.DEVELOPER}


def _is_secret_path(path: Path) -> bool:
    return any(part == ".env" or part.startswith(".env.") for part in path.parts)


class RepositoryMCP:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _result(
        self,
        role: AgentRole,
        tool: str,
        status: ToolStatus,
        output: str = "",
        error: str | None = None,
    ) -> ToolResult:
        return ToolResult(
            tool_name=tool,
            allowed_role=role,
            status=status,
            input_summary="safe",
            output_summary=output,
            duration_ms=0,
            error=error,
        )

    def _path(self, relative: str) -> Path:
        requested = Path(relative)
        if ".." in requested.parts or _is_secret_path(requested):
            raise ValueError("path traversal denied")
        target = (self.root / relative).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError("outside workspace denied")
        return target

    def list_files(self, role: AgentRole) -> ToolResult:
        if role not in _READ_ROLES:
            return self._result(role, "list_files", ToolStatus.DENIED, error="role denied")
        return self._result(
            role,
            "list_files",
            ToolStatus.SUCCESS,
            "\n".join(
                str(p.relative_to(self.root))
                for p in self.root.rglob("*")
                if p.is_file() and not p.is_symlink() and not _is_secret_path(p.relative_to(self.root))
            ),
        )

    def read_file(self, role: AgentRole, relative: str) -> ToolResult:
        if role not in _READ_ROLES:
            return self._result(role, "read_file", ToolStatus.DENIED, error="role denied")
        try:
            return self._result(
                role,
                "read_file",
                ToolStatus.SUCCESS,
                self._path(relative).read_text(encoding="utf-8"),
            )
        except (OSError, ValueError) as exc:
            return self._result(role, "read_file", ToolStatus.DENIED, error=str(exc))

    get_file_content = read_file

    def search_code(self, role: AgentRole, query: str) -> ToolResult:
        if role not in _READ_ROLES:
            return self._result(role, "search_code", ToolStatus.DENIED, error="role denied")
        matches = []
        for path in self.root.rglob("*"):
            try:
                resolved = path.resolve()
                inside = resolved == self.root or self.root in resolved.parents
                if path.is_symlink() or not inside or not resolved.is_file():
                    continue
                if query in resolved.read_text(encoding="utf-8", errors="ignore"):
                    matches.append(str(path.relative_to(self.root)))
            except OSError:
                continue
        return self._result(role, "search_code", ToolStatus.SUCCESS, "\n".join(matches))

    def create_file(self, role: AgentRole, relative: str, content: str) -> ToolResult:
        return self._write(role, "create_file", relative, content, create=True)

    def update_file(self, role: AgentRole, relative: str, content: str) -> ToolResult:
        return self._write(role, "update_file", relative, content, create=False)

    def _write(
        self, role: AgentRole, tool: str, relative: str, content: str, create: bool
    ) -> ToolResult:
        if role not in _WRITE_ROLES:
            return self._result(role, tool, ToolStatus.DENIED, error="role denied")
        try:
            path = self._path(relative)
            if not create and not path.exists():
                return self._result(role, tool, ToolStatus.FAIL, error="file not found")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return self._result(role, tool, ToolStatus.SUCCESS, relative)
        except (OSError, ValueError) as exc:
            return self._result(role, tool, ToolStatus.DENIED, error=str(exc))

    def get_diff(self, role: AgentRole) -> ToolResult:
        if role not in _WRITE_ROLES:
            return self._result(role, "get_diff", ToolStatus.DENIED, error="role denied")
        return self._result(
            role, "get_diff", ToolStatus.SUCCESS, "diff available in isolated workspace"
        )
