from pathlib import PurePosixPath

from engineering_team.contracts.enums import ActionMode, ToolStatus
from engineering_team.contracts.models import ImplementationResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class DeveloperAgent(AgentBase[ImplementationResult]):
    role = "Developer"

    def execute(self, envelope: ContextEnvelope) -> ImplementationResult:
        specification = envelope.state_projection.get("specification")
        architecture = envelope.state_projection.get("architecture")
        repository_results = [
            item for item in envelope.tool_results
            if item.tool_name in {"list_files", "read_file", "search_code", "get_file_content"}
        ]
        inspected_paths: list[str] = []
        for item in repository_results:
            if item.status is not ToolStatus.SUCCESS:
                continue
            if item.tool_name == "list_files":
                inspected_paths.extend(
                    line.strip().replace("\\", "/") for line in item.output_summary.splitlines()
                )
        safe_paths = list(dict.fromkeys(
            path for path in inspected_paths
            if path
            and not PurePosixPath(path).is_absolute()
            and ".." not in PurePosixPath(path).parts
            and not any(
                part == ".env" or part.startswith(".env.")
                for part in PurePosixPath(path).parts
            )
            and "__pycache__" not in PurePosixPath(path).parts
        ))
        evidence = list(dict.fromkeys(
            item.evidence_reference or f"repository:{item.tool_name}"
            for item in repository_results
        ))
        if not safe_paths:
            return ImplementationResult(
                action_mode=ActionMode.PROPOSED,
                changed_files=[],
                diff=(
                    "NO-OP: repository inspection returned no safe file path; "
                    "implementation requires additional bounded repository evidence."
                ),
                evidence=evidence or ["repository inspection returned no safe paths"],
                validation_result=(
                    "NO-OP validation: no proposal can be applied until list_files returns "
                    "an inspected workspace path."
                ),
                security_surface_changed=False,
            )

        components = ", ".join(getattr(architecture, "components", [])) or "current component"
        apis = ", ".join(getattr(architecture, "apis", [])) or "no API change declared"
        data_changes = (
            ", ".join(getattr(architecture, "data_changes", []))
            or "no data change declared"
        )
        decisions = "; ".join(getattr(architecture, "decisions", [])) or "preserve design"
        objective = getattr(specification, "objective", envelope.current_task)
        changed_files = safe_paths[:3]
        proposal = [
            "PROPOSED TECHNICAL CHANGE",
            f"Objective: {objective}",
            f"Components: {components}",
            f"APIs: {apis}",
            f"Data: {data_changes}",
            f"Design decisions: {decisions}",
        ]
        proposal.extend(
            f"--- {path}\n+++ {path}\n@@ proposed @@\n+ Implement the bounded change above."
            for path in changed_files
        )
        security_terms = " ".join((
            getattr(specification, "source_requirement", ""),
            apis,
            data_changes,
            " ".join(getattr(architecture, "risks", [])),
        )).lower()
        return ImplementationResult(
            action_mode=ActionMode.PROPOSED,
            changed_files=changed_files,
            diff="\n".join(proposal),
            evidence=evidence or [f"repository:list_files:{path}" for path in changed_files],
            validation_result=(
                "PROPOSED validation strategy: run_build, run_linter, and run_tests in the "
                f"isolated workspace after applying changes to {len(changed_files)} inspected path(s)."
            ),
            security_surface_changed=any(
                term in security_terms
                for term in ("api", "auth", "owner", "security", "token", "password", "idor")
            ),
        )
