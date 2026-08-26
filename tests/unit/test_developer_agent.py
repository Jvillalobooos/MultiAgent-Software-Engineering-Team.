from pathlib import PurePosixPath

import pytest
from pydantic import ValidationError

from engineering_team.agents.developer import DeveloperAgent
from engineering_team.contracts.enums import ActionMode, AgentRole, ToolStatus
from engineering_team.contracts.models import (
    ArchitectureProposal,
    ImplementationResult,
    ProductSpecification,
    ToolResult,
)
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context


def test_developer_proposal_is_detailed_and_grounded_in_inspected_paths() -> None:
    specification = ProductSpecification(
        objective="Add an authorized transaction-history endpoint",
        actors=["User"],
        business_rules=["return at most five owned transactions"],
        constraints=["preserve authorization"],
        acceptance_criteria=["ownership is enforced"],
        nfrs=["secure"],
        ambiguities=[],
        assumptions=[],
        source_requirement="Return five transactions for the authorized user",
    )
    architecture = ArchitectureProposal(
        components=["transaction API"],
        apis=["GET /transactions"],
        data_changes=["owner-scoped query limit"],
        integrations=[],
        dependencies=[],
        decisions=["enforce ownership before limiting to five"],
        risks=["IDOR"],
        impact="bounded API change",
    )
    inspected = ["app/api.py", "app/models.py"]
    state = EngineeringState(
        run_id="developer-proposal",
        requirement=specification.source_requirement,
        specification=specification,
        architecture=architecture,
        tool_results=[
            ToolResult(
                tool_name="list_files",
                allowed_role=AgentRole.DEVELOPER,
                status=ToolStatus.SUCCESS,
                input_summary="safe",
                output_summary="\n".join(inspected),
                duration_ms=3,
                evidence_reference="mcp://repository/list_files",
            ),
            *[
                ToolResult(
                    tool_name="read_file",
                    allowed_role=AgentRole.DEVELOPER,
                    status=ToolStatus.SUCCESS,
                    input_summary=f"path={path}",
                    output_summary="def transaction_history(owner_id):\n    pass\n",
                    duration_ms=2,
                    evidence_reference="mcp://repository/read_file",
                )
                for path in inspected
            ],
        ],
    )

    result = DeveloperAgent().execute(build_context(AgentRole.DEVELOPER, state, "Developer"))

    assert result.changed_files
    assert set(result.changed_files) <= set(inspected)
    assert "GET /transactions" in result.diff
    assert "owner-scoped query limit" in result.diff
    assert "mcp://repository/list_files" in result.evidence
    assert any("mcp://repository/read_file#" in item for item in result.evidence)
    assert "run_build" in result.validation_result
    assert "run_linter" in result.validation_result
    assert "run_tests" in result.validation_result
    assert result.security_surface_changed is True


def test_generic_form_word_does_not_invent_ui_api_or_security_surface() -> None:
    specification = ProductSpecification(
        objective="Crea una forma de actualizar el perfil",
        actors=["User"], business_rules=[], constraints=[],
        acceptance_criteria=["profile changes"], nfrs=[], ambiguities=[], assumptions=[],
        source_requirement="Crea una forma de actualizar el perfil",
    )
    architecture = ArchitectureProposal(
        components=["profile service"], apis=[], data_changes=[], integrations=[],
        dependencies=[], decisions=["reuse the existing service"], risks=[], impact="bounded",
    )
    state = EngineeringState(
        run_id="generic-form",
        requirement=specification.source_requirement,
        specification=specification,
        architecture=architecture,
        tool_results=[
            ToolResult(
                tool_name="list_files", allowed_role=AgentRole.DEVELOPER,
                status=ToolStatus.SUCCESS, input_summary="safe",
                output_summary="app/profile_service.py", duration_ms=1,
                evidence_reference="mcp://repository/list_files",
            ),
            ToolResult(
                tool_name="read_file", allowed_role=AgentRole.DEVELOPER,
                status=ToolStatus.SUCCESS, input_summary="path=app/profile_service.py",
                output_summary="def update_profile(profile, values):\n    profile.update(values)\n",
                duration_ms=1, evidence_reference="mcp://repository/read_file",
            ),
        ],
    )

    result = DeveloperAgent().execute(build_context(AgentRole.DEVELOPER, state, "Developer"))

    assert result.changed_files == ["app/profile_service.py"]
    assert " UI" not in result.diff
    assert "APIs: no API change declared" in result.diff
    assert result.security_surface_changed is False


def test_structural_references_resolves_python_relative_import() -> None:
    content = "from .service import apply_update\n"
    candidates = ["app/main.py", "app/service.py"]

    refs = DeveloperAgent.structural_references(content, "app/main.py", candidates)

    assert refs == ["app/service.py"]


def test_structural_references_resolves_typescript_relative_import() -> None:
    content = 'import { promote } from "../domain/account-manager";\n'
    candidates = ["src/routes/account.ts", "src/domain/account-manager.ts"]

    refs = DeveloperAgent.structural_references(content, "src/routes/account.ts", candidates)

    assert refs == ["src/domain/account-manager.ts"]


def test_structural_references_resolves_java_like_dotted_import_by_tail_match() -> None:
    content = "import com.example.domain.AccountService;\n"
    candidates = [
        "src/main/java/com/example/api/AccountController.java",
        "src/main/java/com/example/domain/AccountService.java",
    ]

    refs = DeveloperAgent.structural_references(
        content, "src/main/java/com/example/api/AccountController.java", candidates
    )

    assert refs == ["src/main/java/com/example/domain/AccountService.java"]


def test_structural_references_fails_closed_on_ambiguous_same_stem_tail_match() -> None:
    content = "import com.acme.users.AccountService;\n"
    candidates = [
        "src/main/java/com/acme/entry/Gateway.java",
        "src/main/java/com/acme/users/AccountService.java",
        "src/main/java/com/acme/admin/AccountService.java",
    ]

    refs = DeveloperAgent.structural_references(
        content, "src/main/java/com/acme/entry/Gateway.java", candidates
    )

    assert refs == []


def test_structural_references_still_resolves_fully_qualified_path_match() -> None:
    content = "from app.service import apply_update\n"
    candidates = [
        "app/main.py",
        "app/service.py",
        "other_package/service.py",
    ]

    refs = DeveloperAgent.structural_references(content, "app/main.py", candidates)

    assert refs == ["app/service.py"]


def test_match_basename_fails_closed_on_ambiguous_multi_extension_candidates() -> None:
    candidates = {"src/domain/account-manager.js", "src/domain/account-manager.ts"}

    resolved = DeveloperAgent._match_basename(
        PurePosixPath("src/domain/account-manager"), candidates
    )

    assert resolved is None


def test_structural_references_never_fabricates_a_path_outside_the_candidate_set() -> None:
    content = "from ...secret import token\nimport evaluation.reports.old_run\n"
    candidates = ["app/main.py", "app/service.py"]

    refs = DeveloperAgent.structural_references(content, "app/main.py", candidates)

    assert refs == []


def test_rank_paths_never_favors_a_low_information_marker_over_a_referenced_module() -> None:
    ranked = DeveloperAgent.rank_paths(
        ["app/__init__.py", "app/service.py"],
        search_hits=[],
        terms=[],
        structural_boost={"app/service.py"},
    )

    assert ranked[0] == "app/service.py"


def test_developer_contract_rejects_unjustified_empty_proposal() -> None:
    with pytest.raises(ValidationError, match="no-op justification"):
        ImplementationResult(
            action_mode=ActionMode.PROPOSED,
            changed_files=[],
            diff="",
            evidence=[],
            validation_result="not applied",
        )


def test_developer_selects_inspected_transaction_module_not_first_listed_paths() -> None:
    specification = ProductSpecification(
        objective="Return the latest five transactions for the authorized owner",
        actors=["User"],
        business_rules=["scope history by owner_id", "limit results to five"],
        constraints=["prevent IDOR"],
        acceptance_criteria=["cross-user access is denied"],
        nfrs=["secure"], ambiguities=[], assumptions=[],
        source_requirement="authorized transaction history limited to five",
    )
    architecture = ArchitectureProposal(
        components=["transaction service"], apis=["GET /transactions"],
        data_changes=["owner-scoped query with limit 5"], integrations=[], dependencies=[],
        decisions=["authorize owner before querying"], risks=["IDOR"],
        impact="bounded API and query change",
    )
    listed = "README.md\n__init__.py\nmisc.py\napp/transactions.py"
    code = (
        "def transaction_history(connection, owner_id):\n"
        "    return connection.execute('SELECT * FROM transactions').fetchall()\n"
    )
    state = EngineeringState(
        run_id="relevance", requirement=specification.source_requirement,
        specification=specification, architecture=architecture,
        tool_results=[
            ToolResult(
                tool_name="list_files", allowed_role=AgentRole.DEVELOPER,
                status=ToolStatus.SUCCESS, input_summary="safe", output_summary=listed,
                duration_ms=1, evidence_reference="mcp://repository/list_files",
            ),
            ToolResult(
                tool_name="search_code", allowed_role=AgentRole.DEVELOPER,
                status=ToolStatus.SUCCESS, input_summary="query=transaction",
                output_summary="app/transactions.py", duration_ms=1,
                evidence_reference="mcp://repository/search_code",
            ),
            ToolResult(
                tool_name="read_file", allowed_role=AgentRole.DEVELOPER,
                status=ToolStatus.SUCCESS, input_summary="path=app/transactions.py",
                output_summary=code, duration_ms=1,
                evidence_reference="mcp://repository/read_file",
            ),
        ],
    )

    result = DeveloperAgent().execute(build_context(AgentRole.DEVELOPER, state, "Developer"))

    assert result.changed_files == ["app/transactions.py"]
    assert "transaction_history" in result.diff
    assert "owner_id" in result.diff
    assert "GET /transactions" in result.diff
    assert "owner-scoped query with limit 5" in result.diff
    assert "Implement the bounded change above" not in result.diff
    assert any("read_file" in item for item in result.evidence)
    assert result.security_surface_changed is True


def test_python_update_rejects_removal_of_unrelated_function_and_decorated_route() -> None:
    original = (
        "from framework import app\n\n"
        "def keep_helper():\n    return 'old'\n\n"
        "@app.get('/items')\n"
        "def list_items():\n    return []\n"
    )
    proposed = "def new_feature():\n    return True\n"

    allowed, removed = DeveloperAgent.validate_update_preservation(
        "app/main.py", original, proposed
    )

    assert allowed is False
    assert set(removed) == {"function:keep_helper", "route:list_items"}


def test_python_update_accepts_changed_bodies_when_top_level_boundaries_remain() -> None:
    original = (
        "class Counter:\n"
        "    def increment(self):\n        return 0\n\n"
        "def describe():\n    return 'old'\n"
    )
    proposed = (
        "class Counter:\n"
        "    def __init__(self):\n        self.value = 0\n\n"
        "    def increment(self):\n        self.value += 1\n        return self.value\n\n"
        "def describe():\n    return 'new'\n"
    )

    allowed, removed = DeveloperAgent.validate_update_preservation(
        "src/counter.py", original, proposed
    )

    assert allowed is True
    assert removed == []


def test_python_update_accepts_explicit_architecture_removal_intent() -> None:
    original = "def legacy_adapter():\n    return 'old'\n"
    proposed = "def replacement_adapter():\n    return 'new'\n"

    allowed, removed = DeveloperAgent.validate_update_preservation(
        "src/adapters.py",
        original,
        proposed,
        "Architecture decision: remove legacy_adapter after replacing its callers.",
    )

    assert allowed is True
    assert removed == []
