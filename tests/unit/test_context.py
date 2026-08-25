import pytest

from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def test_product_context_excludes_repository_and_secrets() -> None:
    state = EngineeringState(run_id="r1", requirement="feature", repository_context={"secret": "x"})
    envelope = build_context(AgentRole.PRODUCT, state, "analyze")

    assert envelope.state_projection == {"run_id": "r1", "requirement": "feature"}


def test_context_rejects_unknown_fields() -> None:
    state = EngineeringState(run_id="r1", requirement="feature")
    with pytest.raises(ValueError):
        build_context(AgentRole.PRODUCT, state, "analyze", extra_projection={"secret": "x"})
