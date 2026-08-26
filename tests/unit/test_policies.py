import pytest

from engineering_team.contracts.enums import (
    ActionMode,
    AgentRole,
    RemediationCategory,
    ReviewerStatus,
    RouteTarget,
    SecuritySeverity,
    SecurityStatus,
    ToolStatus,
)
from engineering_team.contracts.models import (
    ArchitectureProposal,
    FileMutation,
    ImplementationResult,
    ProductSpecification,
    ReviewerDecision,
    SecurityFinding,
    SecurityReview,
)
from engineering_team.contracts.models import (
    TestResult as EngineeringTestResult,
)
from engineering_team.llm.policies import policy_for, preserves_governed_facts

CHECKLIST = {key: "PASS" for key in (
    "authentication", "authorization", "input_validation", "sensitive_information",
    "secrets", "injection", "access_control", "idor", "logging", "data_protection",
    "api_abuse", "rate_limiting", "owasp",
)}


def _cases():
    product = ProductSpecification(
        objective="change password", actors=["member"], business_rules=["verify current"],
        constraints=["bounded"], acceptance_criteria=["password changes"], nfrs=["safe"],
        ambiguities=[], assumptions=[], source_requirement="change password",
    )
    architecture = ArchitectureProposal(
        components=["service"], apis=[], data_changes=[], integrations=[], dependencies=[],
        decisions=["reuse service"], risks=["credential handling"], impact="bounded",
        evidence_references=["mcp://read/service"],
    )
    implementation = ImplementationResult(
        action_mode=ActionMode.PROPOSED, changed_files=["service.py"], diff="PROPOSED\n+change",
        evidence=["mcp://read/service"], validation_result="run tests",
    )
    finding = SecurityFinding(
        category="authorization", severity=SecuritySeverity.HIGH,
        description="missing authorization", affected_evidence=["diff"],
        recommendation="enforce authorization",
    )
    security = SecurityReview(
        status=SecurityStatus.FAIL, highest_severity=SecuritySeverity.HIGH,
        findings=[finding], recommendations=["enforce authorization"], sources=["scan://1"],
        checklist={**CHECKLIST, "authorization": "FAIL"},
    )
    testing = EngineeringTestResult(
        proposed_tests=["happy"], generated_tests=["tests/test_service.py"],
        executed_tests=["pytest"], actual_results=["1 failed"], status=ToolStatus.FAIL,
        failures=["wrong behavior"], coverage_mapping={"rule": ["test_service"]},
        evidence_references=["mcp://quality/test"],
    )
    reviewer = ReviewerDecision(
        status=ReviewerStatus.REJECTED, score=40, subscores={"testing": 0},
        problems=["tests failed"], reason="repair tests",
        remediation_category=RemediationCategory.TESTING,
        return_to=RouteTarget.DEVELOPER, confidence=1,
        evidence_references=["mcp://quality/test"],
    )
    return [
        (AgentRole.PRODUCT, product,
         product.model_copy(update={
             "actors": ["member", "admin"],
             "acceptance_criteria": ["correct current password is required"],
             "ambiguities": ["policy"],
         }),
         product.model_copy(update={"business_rules": []})),
        (AgentRole.ARCHITECTURE, architecture,
         architecture.model_copy(update={"components": ["service", "audit"], "risks": ["credential handling", "logging"]}),
         architecture.model_copy(update={"risks": []})),
        (AgentRole.DEVELOPER, implementation,
         implementation.model_copy(update={"mutations": [FileMutation(path="service.py", operation="update", content="value = 1\n")]}),
         implementation.model_copy(update={"changed_files": ["invented.py"]})),
        (AgentRole.SECURITY, security,
         security.model_copy(update={"recommendations": ["enforce authorization", "add audit"]}),
         security.model_copy(update={"checklist": CHECKLIST})),
        (AgentRole.TESTING, testing,
         testing.model_copy(update={"proposed_tests": ["happy", "edge"], "test_mutations": [FileMutation(path="tests/test_edge.py", operation="create", content="def test_edge():\n    assert True\n")]}),
         testing.model_copy(update={"failures": []})),
        (AgentRole.REVIEWER, reviewer,
         reviewer.model_copy(update={"score": 35, "reason": "more detail"}),
         reviewer.model_copy(update={"problems": []})),
    ]


@pytest.mark.parametrize(("role", "candidate", "enriched", "weakened"), _cases())
def test_role_policy_allows_grounded_enrichment_but_rejects_weakening(
    role, candidate, enriched, weakened
) -> None:
    policy = policy_for(role, type(candidate))

    assert preserves_governed_facts(candidate.model_dump(mode="json"), enriched, policy)
    assert not preserves_governed_facts(candidate.model_dump(mode="json"), weakened, policy)


@pytest.mark.parametrize(("role", "candidate", "_enriched", "_weakened"), _cases())
def test_every_artifact_field_has_one_central_policy_classification(
    role, candidate, _enriched, _weakened
) -> None:
    policy = policy_for(role, type(candidate))
    classified = (
        set(policy.exact_fields)
        | set(policy.additive_fields)
        | set(policy.enrichable_fields)
        | set(policy.mutation_fields)
        | set(policy.monotonic_fields)
    )

    assert classified == set(type(candidate).model_fields)


def test_security_model_may_strengthen_deterministic_pass_to_fail() -> None:
    baseline = SecurityReview(
        status=SecurityStatus.PASS,
        highest_severity=SecuritySeverity.INFO,
        findings=[],
        recommendations=[],
        sources=["scanner://baseline"],
        checklist=CHECKLIST,
    )
    finding = SecurityFinding(
        category="input_validation",
        severity=SecuritySeverity.HIGH,
        description="unvalidated data reaches a sensitive operation",
        affected_evidence=["mcp://repository/get_diff"],
        recommendation="validate before the operation",
    )
    strengthened = baseline.model_copy(update={
        "status": SecurityStatus.FAIL,
        "highest_severity": SecuritySeverity.HIGH,
        "findings": [finding],
        "recommendations": ["validate before the operation"],
        "sources": ["scanner://baseline", "rag://owasp/input-validation"],
        "checklist": {**CHECKLIST, "input_validation": "FAIL"},
        "requires_hitl": True,
    })

    assert preserves_governed_facts(
        baseline.model_dump(mode="json"),
        strengthened,
        policy_for(AgentRole.SECURITY, SecurityReview),
    )


def test_security_model_may_not_weaken_deterministic_fail_to_pass() -> None:
    finding = SecurityFinding(
        category="authorization",
        severity=SecuritySeverity.HIGH,
        description="authorization is missing",
        affected_evidence=["scanner://finding"],
        recommendation="enforce authorization",
    )
    baseline = SecurityReview(
        status=SecurityStatus.FAIL,
        highest_severity=SecuritySeverity.HIGH,
        findings=[finding],
        recommendations=["enforce authorization"],
        sources=["scanner://finding"],
        checklist={**CHECKLIST, "authorization": "FAIL"},
        requires_hitl=True,
    )
    weakened = baseline.model_copy(update={
        "status": SecurityStatus.PASS,
        "highest_severity": SecuritySeverity.INFO,
        "checklist": CHECKLIST,
        "requires_hitl": False,
    })

    assert not preserves_governed_facts(
        baseline.model_dump(mode="json"),
        weakened,
        policy_for(AgentRole.SECURITY, SecurityReview),
    )
