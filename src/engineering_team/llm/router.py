from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole

from .registry import ModelRegistry, ModelSelection


class ModelRouter:
    """Deterministic role-to-model authority."""

    def __init__(self, settings: Settings) -> None:
        self._registry = ModelRegistry(settings)

    def local_for(self, agent: AgentRole) -> ModelSelection:
        return self._registry.local_selection(agent)
