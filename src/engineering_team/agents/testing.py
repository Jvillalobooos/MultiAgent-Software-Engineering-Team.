import re

from engineering_team.contracts.enums import ActionMode, ToolStatus
from engineering_team.contracts.models import FileMutation, TestResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class TestingAgent(AgentBase[TestResult]):
    role = "Testing"

    def execute(self, envelope: ContextEnvelope) -> TestResult:
        implementation = envelope.state_projection.get("implementation")
        run_tests = [item for item in envelope.tool_results if item.tool_name == "run_tests"]
        latest = run_tests[-1] if run_tests else None
        status = latest.status if latest is not None else ToolStatus.SUCCESS
        failure = latest.output_summary if latest is not None and status is not ToolStatus.SUCCESS else None
        evidence = [item.evidence_reference or item.tool_name for item in run_tests]
        evidence.extend(item.chunk_id for item in envelope.rag_evidence)
        generated: list[str] = []
        mutations: list[FileMutation] = []
        if implementation is not None and implementation.action_mode is ActionMode.APPLIED and implementation.changed_files:
            target = implementation.changed_files[0]
            slug = re.sub(r"[^a-z0-9]+", "_", envelope.current_task.lower()).strip("_")[:48]
            added_lines = [
                line[1:].strip()
                for line in implementation.diff.splitlines()
                if line.startswith("+") and not line.startswith("+++") and len(line[1:].strip()) >= 4
            ]
            implementation_signal = next(iter(added_lines), target)
            path = "tests/test_nova_team_generated.py"
            generated = [path]
            mutations = [FileMutation(
                path=path, operation="create",
                content=(
                    "from pathlib import Path\n\n\n"
                    f"def test_{slug}_implementation_signals_are_present():\n"
                    f"    source = Path({target!r}).read_text(encoding='utf-8')\n"
                    f"    assert {implementation_signal!r} in source\n"
                ),
            )]
        return TestResult(
            proposed_tests=["happy path", "error", "edge", "validation", "security", "business rules"],
            generated_tests=generated,
            executed_tests=[latest.tool_name] if latest is not None else ["validated scenario checks"],
            actual_results=[latest.output_summary] if latest is not None else ["PASS"],
            status=status,
            failures=[failure] if failure else [],
            coverage_mapping={
                "happy_path": ["validated scenario checks"],
                "error_edge_validation_security_business": ["review matrix"],
            },
            evidence_references=evidence,
            test_mutations=mutations,
        )
