"""The Testing agent must report coverage it can evidence, and nothing more.

Before these tests it returned a hardcoded six-item list and a `coverage_mapping`
pointing at the literal string "review matrix", which claimed error, validation,
security and business-rule coverage on every run regardless of what executed.
"""

from engineering_team.agents.testing import TestingAgent
from engineering_team.contracts.enums import AgentRole, ToolStatus
from engineering_team.contracts.models import ProductSpecification, ToolResult
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def _specification(**overrides: object) -> ProductSpecification:
    base: dict[str, object] = {
        "objective": "Lock an account after repeated failures",
        "actors": ["User"],
        "business_rules": ["lock the account after five consecutive failed attempts"],
        "constraints": ["the message must not reveal that the account is locked"],
        "acceptance_criteria": [
            "a correct password is rejected while the account is locked",
            "an invalid password increments the counter",
        ],
        "nfrs": [],
        "ambiguities": [],
        "assumptions": [],
        "source_requirement": "Lock the account after five failed attempts",
    }
    base.update(overrides)
    return ProductSpecification(**base)  # type: ignore[arg-type]


def _run(specification: ProductSpecification, tools: list[ToolResult]):
    state = EngineeringState(
        run_id="testing-coverage",
        requirement=specification.source_requirement,
        specification=specification,
        tool_results=tools,
    )
    return TestingAgent().execute(build_context(AgentRole.TESTING, state, "Testing"))


def _tool(summary: str, *, evidence: str | None = None, status: ToolStatus = ToolStatus.SUCCESS) -> ToolResult:
    return ToolResult(
        tool_name="run_tests",
        allowed_role=AgentRole.TESTING,
        input_summary="pytest -q",
        status=status,
        output_summary=summary,
        duration_ms=120,
        evidence_reference=evidence,
    )


def test_required_coverage_is_derived_from_the_specification_not_hardcoded() -> None:
    """A spec about locking and rejection implies security and error dimensions; a spec
    with none of that must not claim them."""
    rich = _run(_specification(), [_tool("5 passed")])
    assert "security" in rich.proposed_tests
    assert "error" in rich.proposed_tests

    plain = _run(
        _specification(
            business_rules=["render the dashboard"],
            constraints=[],
            acceptance_criteria=["the dashboard lists the accounts"],
        ),
        [_tool("1 passed")],
    )
    # The plain spec still states a business rule, so that dimension is genuinely
    # required -- but nothing in it implies security, errors or boundaries.
    assert plain.proposed_tests == ["business_rule", "happy_path"]
    assert "security" not in plain.proposed_tests
    assert "error" not in plain.proposed_tests


def test_every_covered_dimension_points_at_recorded_evidence() -> None:
    result = _run(
        _specification(),
        [
            _tool("4 passed", evidence="tests/test_bloqueo.py::test_quinto_intento_bloquea"),
            _tool("ok", evidence="tests/test_bloqueo.py::test_password_correcta_es_rechazada"),
        ],
    )
    recorded = set(result.executed_tests)
    for dimension, evidence in result.coverage_mapping.items():
        for reference in evidence:
            assert reference in recorded, f"{dimension} cites evidence the run never recorded"


def test_a_dimension_with_no_matching_test_is_reported_as_a_gap() -> None:
    """The old implementation filled every dimension with a placeholder. An uncovered
    dimension must stay empty and be named in `failures`."""
    result = _run(
        _specification(
            acceptance_criteria=["the maximum page size is respected"],
            business_rules=["never return more than one hundred rows"],
            constraints=[],
        ),
        [_tool("1 passed", evidence="tests/test_listado.py::test_camino_feliz")],
    )
    assert "boundary" in result.proposed_tests
    assert result.coverage_mapping["boundary"] == []
    assert any("boundary" in failure for failure in result.failures)


def test_a_coverage_gap_does_not_turn_a_green_suite_red() -> None:
    """`status` reports what the suite did. A gap is missing evidence, which the
    reviewer weighs separately -- conflating them would reject working changes."""
    result = _run(
        _specification(),
        [_tool("1 passed", evidence="tests/test_x.py::test_camino_feliz")],
    )
    assert result.status is ToolStatus.SUCCESS
    assert result.failures, "gaps should still be reported"


def test_a_failing_suite_reports_the_failure_first() -> None:
    result = _run(
        _specification(),
        [_tool("2 failed", evidence="tests/test_bloqueo.py", status=ToolStatus.FAIL)],
    )
    assert result.status is ToolStatus.FAIL
    assert result.failures[0] == "2 failed"


def test_without_any_executed_suite_nothing_is_claimed_as_covered() -> None:
    result = _run(_specification(), [])
    assert result.executed_tests == ["no run_tests evidence recorded"]
    assert all(evidence == [] for evidence in result.coverage_mapping.values())
    assert result.actual_results == ["no suite executed"]
