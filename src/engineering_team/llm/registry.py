from dataclasses import dataclass
from typing import ClassVar

from engineering_team.config import Settings
from engineering_team.contracts.enums import AgentRole


@dataclass(frozen=True)
class ModelSelection:
    agent: AgentRole
    model_profile: str
    provider: str
    model: str


class ModelRegistry:
    """The only source of configured model IDs; agents never own identifiers."""

    _profiles: ClassVar[dict[AgentRole, str]] = {
        AgentRole.PRODUCT: "DEEP_MODEL",
        AgentRole.ARCHITECTURE: "FAST_MODEL",
        AgentRole.DEVELOPER: "CODING_MODEL",
        AgentRole.SECURITY: "DEEP_MODEL",
        AgentRole.TESTING: "FAST_MODEL",
        AgentRole.REVIEWER: "DEEP_MODEL",
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def local_selection(self, agent: AgentRole) -> ModelSelection:
        profile = self._profiles[agent]
        model = {
            "FAST_MODEL": self._settings.fast_model,
            "DEEP_MODEL": self._settings.deep_model,
            "CODING_MODEL": self._settings.coding_model,
        }[profile]
        return ModelSelection(agent=agent, model_profile=profile, provider="ollama", model=model)
