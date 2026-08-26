"""Persist validated Product and Architecture decisions in a run workspace."""

from collections.abc import Iterable
from pathlib import Path

from engineering_team.contracts.models import ArchitectureProposal, ProductSpecification


def _section(title: str, values: Iterable[str]) -> str:
    items = list(values)
    body = "\n".join(f"- {value}" for value in items) if items else "- None recorded."
    return f"## {title}\n\n{body}\n"


def _write(workspace: str | Path, filename: str, content: str) -> Path:
    destination = Path(workspace) / "docs" / "decisions" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    return destination


def write_product_specification(
    workspace: str | Path, requirement: str, specification: ProductSpecification
) -> Path:
    content = "\n".join((
        "# Product Specification\n",
        "## Source Requirement\n\n" + requirement + "\n",
        "## Objective\n\n" + specification.objective + "\n",
        _section("Actors", specification.actors),
        _section("Business Rules", specification.business_rules),
        _section("Constraints", specification.constraints),
        _section("Acceptance Criteria", specification.acceptance_criteria),
        _section("Non-functional Requirements", specification.nfrs),
        _section("Ambiguities", specification.ambiguities),
        _section("Assumptions", specification.assumptions),
    ))
    return _write(workspace, "product-specification.md", content)


def write_architecture_decisions(
    workspace: str | Path, requirement: str, architecture: ArchitectureProposal
) -> Path:
    content = "\n".join((
        "# Architecture Decisions\n",
        "## Source Requirement\n\n" + requirement + "\n",
        "## Impact\n\n" + architecture.impact + "\n",
        _section("Components", architecture.components),
        _section("APIs", architecture.apis),
        _section("Data Changes", architecture.data_changes),
        _section("Integrations", architecture.integrations),
        _section("Dependencies", architecture.dependencies),
        _section("Decisions", architecture.decisions),
        _section("Risks", architecture.risks),
        _section("Evidence References", architecture.evidence_references),
    ))
    return _write(workspace, "architecture-decisions.md", content)
