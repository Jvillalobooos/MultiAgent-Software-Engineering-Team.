from engineering_team.contracts.models import ProductSpecification
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase


class ProductAgent(AgentBase[ProductSpecification]):
    role = "Product"

    def execute(self, envelope: ContextEnvelope) -> ProductSpecification:
        requirement = str(envelope.state_projection["requirement"])
        lowered = requirement.lower()
        rules: list[str] = []
        if "15" in lowered and ("single-use" in lowered or "only once" in lowered):
            rules.extend(["Reset link expires after 15 minutes", "Reset link is single-use"])
        if "five failed" in lowered or "5 failed" in lowered:
            rules.append("Account locks after exactly 5 failed attempts")
        if "latest five" in lowered or "maximum five" in lowered:
            rules.extend(["Only the authorized user's transactions", "Maximum 5 transactions"])
        return ProductSpecification(
            objective=requirement,
            actors=["User"],
            business_rules=rules,
            constraints=[],
            acceptance_criteria=rules or ["Requirement is fulfilled"],
            nfrs=[],
            ambiguities=[],
            assumptions=[],
            source_requirement=requirement,
        )
