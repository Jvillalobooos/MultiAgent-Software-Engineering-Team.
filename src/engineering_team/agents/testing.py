"""Testing agent: derives the coverage a change is required to demonstrate from the
product specification, then reports how much of it the executed suite actually shows.

Deliberately deterministic. Classification is keyword-driven rather than model-driven so
the coverage claim is reproducible and auditable: the same specification and the same
executed tests always produce the same mapping, and every entry points at evidence the
run really recorded. A dimension with no matching evidence is reported empty; it is
never filled with a placeholder.
"""

from engineering_team.contracts.enums import ToolStatus
from engineering_team.contracts.models import TestResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase

# `happy_path` is always required. Every other dimension is required only when the
# specification actually implies it, so the claim stays specific to the change.
_ALWAYS_REQUIRED = ("happy_path",)

_MARKERS: dict[str, tuple[str, ...]] = {
    "boundary": (
        "limit", "límite", "limite", "maximum", "máximo", "maximo", "minimum", "mínimo",
        "minimo", "boundary", "exceed", "excede", "empty", "vacío", "vacio", "zero",
        "cero", "tope", "length", "longitud", "range", "rango", "overflow",
    ),
    "error": (
        "error", "fail", "falla", "fallo", "reject", "rechaz", "invalid", "inválid",
        "denied", "denegad", "exception", "excepción", "not found", "no encontrad",
        "incorrect", "incorrect", "raises", "lanza",
    ),
    "validation": (
        "valid", "válid", "format", "formato", "required", "requerid", "obligatori",
        "type", "tipo", "sanitiz", "allowed", "permitid", "must be", "debe ser",
    ),
    "security": (
        "authoriz", "autoriz", "permission", "permiso", "token", "expire", "expira",
        "owner", "dueñ", "propiedad", "session", "sesión", "sesion", "credential",
        "credencial", "password", "contraseñ", "lock", "bloque", "attempt", "intento",
        "enumerat", "enumerac", "single use", "un solo uso", "ajen", "idor",
    ),
    "business_rule": (),  # filled from the specification's own business rules
}


def _normalise(text: object) -> str:
    return " ".join(str(text).lower().split())


def _business_terms(rules: list[str]) -> tuple[str, ...]:
    """Distinctive words drawn from the specification's stated business rules.

    Short and common words are dropped, so a rule cannot match every sentence in the
    suite and a hit is genuine evidence rather than coincidence.
    """
    terms: set[str] = set()
    for rule in rules:
        for word in _normalise(rule).replace("_", " ").split():
            cleaned = "".join(character for character in word if character.isalnum())
            if len(cleaned) >= 6:
                terms.add(cleaned)
    return tuple(sorted(terms))


def _categories_for(text: str, business_terms: tuple[str, ...]) -> set[str]:
    """Every dimension one sentence or test identifier speaks to."""
    found = {name for name, markers in _MARKERS.items() if any(m in text for m in markers)}
    if business_terms and any(term in text for term in business_terms):
        found.add("business_rule")
    return found


class TestingAgent(AgentBase[TestResult]):
    role = "Testing"

    def execute(self, envelope: ContextEnvelope) -> TestResult:
        run_tests = [item for item in envelope.tool_results if item.tool_name == "run_tests"]
        latest = run_tests[-1] if run_tests else None
        status = latest.status if latest is not None else ToolStatus.SUCCESS

        specification = envelope.state_projection.get("specification")
        criteria: list[str] = []
        rules: list[str] = []
        if specification is not None:
            criteria = list(getattr(specification, "acceptance_criteria", None) or [])
            criteria.extend(getattr(specification, "constraints", None) or [])
            criteria.extend(getattr(specification, "nfrs", None) or [])
            rules = list(getattr(specification, "business_rules", None) or [])
        business_terms = _business_terms(rules)

        # 1. What the specification requires this change to demonstrate.
        required: set[str] = set(_ALWAYS_REQUIRED)
        for sentence in (*criteria, *rules):
            required |= _categories_for(_normalise(sentence), business_terms)

        # 2. What the run actually executed, named by the evidence it produced.
        executed = [item.evidence_reference or item.tool_name for item in run_tests]
        summary = _normalise(latest.output_summary) if latest is not None else ""

        # 3. Which required dimension each piece of evidence demonstrates.
        coverage: dict[str, list[str]] = {name: [] for name in sorted(required)}
        for name in executed:
            for dimension in _categories_for(_normalise(name), business_terms) & required:
                coverage[dimension].append(name)
        if latest is not None and status is ToolStatus.SUCCESS:
            # A green suite is direct evidence of the happy path even when the runner
            # reports one aggregate result instead of per-test identifiers.
            reference = latest.evidence_reference or latest.tool_name
            for dimension in ({"happy_path"} | _categories_for(summary, business_terms)) & required:
                if not coverage[dimension]:
                    coverage[dimension].append(reference)

        gaps = sorted(name for name, evidence in coverage.items() if not evidence)

        failures: list[str] = []
        if latest is not None and status is not ToolStatus.SUCCESS:
            failures.append(latest.output_summary)
        # Gaps are reported as findings, not as a verdict: `status` still comes from the
        # suite's own result. Missing evidence and a test that ran and failed are
        # different facts, and the reviewer weighs them differently.
        failures.extend(f"no executed test demonstrates {name}" for name in gaps)

        evidence_references = list(executed)
        evidence_references.extend(item.chunk_id for item in envelope.rag_evidence)

        return TestResult(
            proposed_tests=sorted(required),
            generated_tests=[],
            executed_tests=executed or ["no run_tests evidence recorded"],
            actual_results=[latest.output_summary] if latest is not None else ["no suite executed"],
            status=status,
            failures=failures,
            coverage_mapping=coverage,
            evidence_references=evidence_references,
        )
