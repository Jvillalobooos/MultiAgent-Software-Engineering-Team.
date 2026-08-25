from engineering_team.contracts.enums import ActionMode
from engineering_team.contracts.models import ImplementationResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class DeveloperAgent(AgentBase[ImplementationResult]):
    role = "Developer"

    def execute(self, envelope: ContextEnvelope) -> ImplementationResult:
        return ImplementationResult(
            action_mode=ActionMode.PROPOSED,
            changed_files=[],
            diff="",
            evidence=[],
            validation_result="not applied",
        )
