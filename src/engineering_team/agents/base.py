from typing import Generic, TypeVar

from pydantic import BaseModel

from engineering_team.models.context import ContextEnvelope

T = TypeVar("T", bound=BaseModel)


class AgentBase(Generic[T]):
    role: str

    def execute(self, envelope: ContextEnvelope) -> T:
        raise NotImplementedError
