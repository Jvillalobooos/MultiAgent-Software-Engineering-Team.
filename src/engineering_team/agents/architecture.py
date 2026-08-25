from engineering_team.contracts.models import ArchitectureProposal
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class ArchitectureAgent(AgentBase[ArchitectureProposal]):
    role = "Architecture"

    def execute(self, envelope: ContextEnvelope) -> ArchitectureProposal:
        sources = [item.chunk_id for item in envelope.rag_evidence]
        return ArchitectureProposal(
            components=["modular monolith"],
            apis=[],
            data_changes=[],
            integrations=[],
            dependencies=[],
            decisions=["preserve modular boundaries"],
            risks=[],
            impact="bounded",
            evidence_references=sources,
        )
