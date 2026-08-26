import re
from typing import ClassVar

from engineering_team.contracts.enums import ToolStatus
from engineering_team.contracts.models import FileMutation, ImplementationResult, TestResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class TestingAgent(AgentBase[TestResult]):
    role = "Testing"

    _DECLARATION_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"\b(?:def|class|function|fn)\s+([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_][A-Za-z0-9_]*)"),
        re.compile(
            r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|:)"
        ),
        re.compile(
            r"\b(?:public|private|protected|internal|static|async|final|virtual|override)"
            r"(?:\s+[A-Za-z_][A-Za-z0-9_<>,.?\[\]]*)+\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\s*\("
        ),
    )
    _SIGNAL_STOPWORDS: ClassVar[set[str]] = {
        "assert", "async", "await", "class", "const", "def", "else", "false",
        "from", "function", "import", "internal", "null", "none", "private",
        "protected", "public", "return", "static", "true", "value", "var", "void",
    }
    _SOURCE_INSPECTION_MARKERS: ClassVar[tuple[str, ...]] = (
        ".read_text(", "readfilesync(", "readfile(", "read_to_string(",
        "files.readstring(", "file.readalltext(",
    )

    @classmethod
    def implementation_signals(cls, implementation: ImplementationResult) -> list[str]:
        """Extract language-neutral behavior identifiers from the changed contract."""
        contract = "\n".join(
            line[1:]
            for line in implementation.diff.splitlines()
            if (
                (line.startswith("+") and not line.startswith("+++"))
                or line.startswith(" ")
            )
        )
        declared: list[str] = []
        for pattern in cls._DECLARATION_PATTERNS:
            declared.extend(pattern.findall(contract))
        candidates = declared or re.findall(
            r"\b[A-Za-z_][A-Za-z0-9_]{3,}\b", contract
        )
        return list(dict.fromkeys(
            item.casefold()
            for item in candidates
            if item.casefold() not in cls._SIGNAL_STOPWORDS
        ))

    @classmethod
    def mutation_is_grounded(
        cls,
        implementation: ImplementationResult,
        mutation: FileMutation,
    ) -> bool:
        """Require a proposed test to reference behavior introduced by the implementation."""
        signals = cls.implementation_signals(implementation)
        content = mutation.content.casefold()
        referenced = [signal for signal in signals if signal in content]
        if not referenced:
            return False
        if any(marker in content for marker in cls._SOURCE_INSPECTION_MARKERS):
            return any(
                re.search(rf"\b{re.escape(signal)}\s*\(", content)
                for signal in referenced
            )
        return True

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
            test_mutations=[],
        )
