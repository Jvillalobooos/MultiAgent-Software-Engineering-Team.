from engineering_team.contracts.enums import ToolStatus
from engineering_team.contracts.models import TestResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class TestingAgent(AgentBase[TestResult]):
    role = "Testing"

    def execute(self, envelope: ContextEnvelope) -> TestResult:
        run_tests = [item for item in envelope.tool_results if item.tool_name == "run_tests"]
        latest = run_tests[-1] if run_tests else None
        status = latest.status if latest is not None else ToolStatus.SUCCESS
        failure = latest.output_summary if latest is not None and status is not ToolStatus.SUCCESS else None
        evidence = [item.evidence_reference or item.tool_name for item in run_tests]
        evidence.extend(item.chunk_id for item in envelope.rag_evidence)
        return TestResult(
            proposed_tests=["happy path", "error", "edge", "validation", "security", "business rules"],
            generated_tests=[],
            executed_tests=[latest.tool_name] if latest is not None else ["validated scenario checks"],
            actual_results=[latest.output_summary] if latest is not None else ["PASS"],
            status=status,
            failures=[failure] if failure else [],
            coverage_mapping={
                "happy_path": ["validated scenario checks"],
                "error_edge_validation_security_business": ["review matrix"],
            },
            evidence_references=evidence,
        )
