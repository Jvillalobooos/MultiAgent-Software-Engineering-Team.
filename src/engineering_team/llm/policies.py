"""Central field-preservation policies for model-produced artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from engineering_team.contracts.enums import AgentRole
from engineering_team.contracts.models import (
    ArchitectureProposal,
    ImplementationResult,
    ProductSpecification,
    ReviewerDecision,
    SecurityReview,
    TestResult,
)


@dataclass(frozen=True)
class ArtifactPolicy:
    exact_fields: tuple[str, ...] = ()
    additive_fields: tuple[str, ...] = ()
    enrichable_fields: tuple[str, ...] = ()
    mutation_fields: tuple[str, ...] = ()
    monotonic_fields: tuple[str, ...] = ()

    def prompt_instruction(self) -> str:
        def names(values: tuple[str, ...]) -> str:
            return ", ".join(values) if values else "none"

        return (
            "FIELD POLICY: preserve exact fields unchanged "
            f"[{names(self.exact_fields)}]; additive fields may add grounded items but must "
            f"retain every candidate item [{names(self.additive_fields)}]; enrichable fields "
            f"may be refined only from supplied evidence [{names(self.enrichable_fields)}]; "
            f"only mutation fields may replace their candidate value [{names(self.mutation_fields)}]; "
            "monotonic fields may only become more restrictive/severe from grounded evidence "
            f"[{names(self.monotonic_fields)}]."
        )


_POLICIES: dict[tuple[AgentRole, type[BaseModel]], ArtifactPolicy] = {
    (AgentRole.PRODUCT, ProductSpecification): ArtifactPolicy(
        exact_fields=("source_requirement",),
        additive_fields=(
            "actors",
            "business_rules",
            "constraints",
            "nfrs",
            "ambiguities",
            "assumptions",
        ),
        enrichable_fields=("objective", "acceptance_criteria"),
    ),
    (AgentRole.ARCHITECTURE, ArchitectureProposal): ArtifactPolicy(
        exact_fields=("evidence_references",),
        additive_fields=(
            "components",
            "apis",
            "data_changes",
            "integrations",
            "dependencies",
            "decisions",
            "risks",
        ),
        enrichable_fields=("impact",),
    ),
    (AgentRole.DEVELOPER, ImplementationResult): ArtifactPolicy(
        exact_fields=(
            "action_mode",
            "changed_files",
            "diff",
            "evidence",
            "validation_result",
            "security_surface_changed",
        ),
        mutation_fields=("mutations", "blocker"),
    ),
    (AgentRole.SECURITY, SecurityReview): ArtifactPolicy(
        additive_fields=("findings", "recommendations", "sources"),
        monotonic_fields=("status", "highest_severity", "checklist", "requires_hitl"),
    ),
    (AgentRole.TESTING, TestResult): ArtifactPolicy(
        exact_fields=(
            "generated_tests",
            "executed_tests",
            "actual_results",
            "status",
            "evidence_references",
        ),
        additive_fields=("proposed_tests", "failures"),
        enrichable_fields=("coverage_mapping",),
        mutation_fields=("test_mutations",),
    ),
    (AgentRole.REVIEWER, ReviewerDecision): ArtifactPolicy(
        exact_fields=(
            "status",
            "remediation_category",
            "return_to",
            "evidence_references",
        ),
        additive_fields=("problems",),
        enrichable_fields=("score", "subscores", "reason", "confidence"),
    ),
}


def policy_for(role: AgentRole, artifact_type: type[BaseModel]) -> ArtifactPolicy:
    try:
        return _POLICIES[(role, artifact_type)]
    except KeyError as exc:
        raise ValueError(
            f"no artifact policy for {role.value}/{artifact_type.__name__}"
        ) from exc


def preserves_governed_facts(
    candidate: dict[str, object],
    parsed: BaseModel,
    policy: ArtifactPolicy,
) -> bool:
    """Reject schema-valid output that weakens deterministic candidate facts."""
    actual = parsed.model_dump(mode="json")
    if any(actual.get(field) != candidate.get(field) for field in policy.exact_fields):
        return False
    for field in policy.additive_fields:
        expected = candidate.get(field)
        received = actual.get(field)
        if isinstance(expected, list) and isinstance(received, list):
            if not all(item in received for item in expected):
                return False
        elif isinstance(expected, dict) and isinstance(received, dict):
            if any(received.get(key) != value for key, value in expected.items()):
                return False
        elif received != expected:
            return False
    severity_rank = {
        "INFO": 0,
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }
    binary_rank = {False: 0, True: 1, "PASS": 0, "FAIL": 1}
    for field in policy.monotonic_fields:
        expected = candidate.get(field)
        received = actual.get(field)
        if field == "highest_severity":
            if expected not in severity_rank or received not in severity_rank:
                return False
            if severity_rank[received] < severity_rank[expected]:
                return False
        elif field == "checklist":
            if not isinstance(expected, dict) or not isinstance(received, dict):
                return False
            if set(received) != set(expected):
                return False
            if any(
                value not in binary_rank
                or received.get(key) not in binary_rank
                or binary_rank[received[key]] < binary_rank[value]
                for key, value in expected.items()
            ):
                return False
        elif expected not in binary_rank or received not in binary_rank or binary_rank[received] < binary_rank[expected]:
            return False
    return True
