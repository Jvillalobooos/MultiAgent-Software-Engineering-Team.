import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engineering_team.capabilities import (
    command_for,
    detect_project_capabilities,
    is_native_test_path,
)
from engineering_team.contracts.enums import ProjectCapabilityStatus, ProjectEcosystem
from engineering_team.contracts.models import ProjectCapabilityProfile, ProjectCommand
from engineering_team.contracts.state import EngineeringState


def _python_profile(**updates) -> ProjectCapabilityProfile:
    values = {
        "status": ProjectCapabilityStatus.SUPPORTED,
        "ecosystem": ProjectEcosystem.PYTHON,
        "project_root": ".",
        "manifests": ["pyproject.toml"],
        "source_suffixes": [".py"],
        "test_path_patterns": ["test_*.py", "tests/**/*.py"],
        "commands": {
            "test": ProjectCommand(
                argv=["python", "-m", "pytest"],
                accepts_paths=True,
                cwd=".",
            ),
        },
        "required_capabilities": ["test"],
        "missing_capabilities": [],
        "evidence_references": ["mcp://repository/detect_project_capabilities"],
    }
    values.update(updates)
    return ProjectCapabilityProfile.create(**values)


def test_profile_create_builds_stable_canonical_fingerprint() -> None:
    first = _python_profile(evidence_references=["evidence:first"])
    second = _python_profile(evidence_references=["evidence:second"])

    assert len(first.fingerprint) == 64
    assert first.fingerprint == second.fingerprint


def test_profile_rejects_tampered_fingerprint() -> None:
    payload = _python_profile().model_dump(mode="json")
    payload["fingerprint"] = "0" * 64

    with pytest.raises(ValidationError, match="fingerprint"):
        ProjectCapabilityProfile.model_validate(payload)


@pytest.mark.parametrize("argv", [[], [""]])
def test_project_command_rejects_empty_argv(argv: list[str]) -> None:
    with pytest.raises(ValidationError, match="argv"):
        ProjectCommand(argv=argv, accepts_paths=False, cwd=".")


@pytest.mark.parametrize("cwd", ["../outside", str(Path.cwd().anchor or "C:\\")])
def test_project_command_rejects_unsafe_cwd(cwd: str) -> None:
    with pytest.raises(ValidationError, match="cwd"):
        ProjectCommand(argv=["tool"], accepts_paths=False, cwd=cwd)


def test_supported_profile_requires_every_mandatory_command() -> None:
    with pytest.raises(ValidationError, match="required capability"):
        _python_profile(commands={}, required_capabilities=["test"])


def test_engineering_state_carries_typed_project_capabilities() -> None:
    profile = _python_profile()

    state = EngineeringState(
        run_id="capabilities",
        requirement="safe change",
        project_capabilities=profile,
    )

    assert state.project_capabilities is profile


@pytest.mark.parametrize(
    ("files", "ecosystem", "test_argv", "build_required"),
    [
        ({"app/main.py": "value = 1\n"}, "python", "pytest", False),
        (
            {
                "package.json": json.dumps({
                    "scripts": {"test": "vitest run", "build": "tsc", "lint": "eslint ."}
                }),
                "tsconfig.json": "{}",
                "src/main.ts": "export const value = 1;\n",
            },
            "node",
            "test",
            True,
        ),
        ({"src/App.csproj": "<Project />"}, "dotnet", "test", True),
        ({"pom.xml": "<project />"}, "java", "test", True),
        ({"build.gradle": "plugins {}\n"}, "java", "test", True),
        ({"go.mod": "module example.test\n"}, "go", "test", True),
        ({"Cargo.toml": "[package]\nname='demo'\nversion='0.1.0'\n"}, "rust", "test", True),
    ],
)
def test_detector_derives_supported_ecosystem_commands(
    tmp_path: Path,
    files: dict[str, str],
    ecosystem: str,
    test_argv: str,
    build_required: bool,
) -> None:
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    profile = detect_project_capabilities(tmp_path)

    assert profile.status is ProjectCapabilityStatus.SUPPORTED
    assert profile.ecosystem.value == ecosystem
    assert test_argv in profile.commands["test"].argv
    assert ("build" in profile.required_capabilities) is build_required


def test_detector_marks_hybrid_and_unknown_projects_without_commands(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )

    hybrid = detect_project_capabilities(tmp_path)
    unknown_root = tmp_path / "unknown"
    unknown_root.mkdir()
    (unknown_root / "README.md").write_text("unknown", encoding="utf-8")
    unknown = detect_project_capabilities(unknown_root)

    assert hybrid.status is ProjectCapabilityStatus.AMBIGUOUS
    assert hybrid.commands == {}
    assert unknown.status is ProjectCapabilityStatus.UNSUPPORTED
    assert unknown.ecosystem is ProjectEcosystem.UNKNOWN
    assert unknown.commands == {}


def test_node_without_declared_test_script_is_unsupported(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"build": "tsc"}}), encoding="utf-8"
    )

    profile = detect_project_capabilities(tmp_path)

    assert profile.status is ProjectCapabilityStatus.UNSUPPORTED
    assert profile.ecosystem is ProjectEcosystem.NODE
    assert "test command" in " ".join(profile.missing_capabilities)


def test_detector_ignores_generated_python_when_node_manifest_exists(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "node --test"}}), encoding="utf-8"
    )
    generated = tmp_path / "node_modules" / "tool.py"
    generated.parent.mkdir()
    generated.write_text("value = 1\n", encoding="utf-8")

    profile = detect_project_capabilities(tmp_path)

    assert profile.ecosystem is ProjectEcosystem.NODE
    assert all("node_modules" not in item for item in profile.manifests)


def test_native_test_paths_and_path_arguments_are_profile_guarded(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    profile = detect_project_capabilities(tmp_path)

    assert is_native_test_path(profile, "tests/test_feature.py") is True
    assert is_native_test_path(profile, "app/service.py") is False
    assert command_for(profile, "test", ["tests/test_feature.py"])[-1] == (
        "tests/test_feature.py"
    )
    with pytest.raises(ValueError, match="native test path"):
        command_for(profile, "test", ["app/service.py"])
