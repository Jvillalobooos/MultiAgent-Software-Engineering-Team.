from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from engineering_team.contracts.enums import (
    ProjectCapabilityStatus,
    ProjectEcosystem,
)
from engineering_team.contracts.models import ProjectCapabilityProfile, ProjectCommand

GENERATED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "evaluation",
    "node_modules",
    "target",
    "workspace",
}

MANIFEST_NAMES: dict[str, ProjectEcosystem] = {
    "pyproject.toml": ProjectEcosystem.PYTHON,
    "pytest.ini": ProjectEcosystem.PYTHON,
    "setup.cfg": ProjectEcosystem.PYTHON,
    "setup.py": ProjectEcosystem.PYTHON,
    "package.json": ProjectEcosystem.NODE,
    "pom.xml": ProjectEcosystem.JAVA,
    "build.gradle": ProjectEcosystem.JAVA,
    "build.gradle.kts": ProjectEcosystem.JAVA,
    "go.mod": ProjectEcosystem.GO,
    "cargo.toml": ProjectEcosystem.RUST,
}


def manifest_ecosystem(path: Path) -> ProjectEcosystem | None:
    name = path.name.casefold()
    if name.endswith((".sln", ".csproj", ".fsproj")):
        return ProjectEcosystem.DOTNET
    return MANIFEST_NAMES.get(name)


def _command(argv: list[str], cwd: str, *, accepts_paths: bool = False) -> ProjectCommand:
    return ProjectCommand(argv=argv, accepts_paths=accepts_paths, cwd=cwd)


def _node_scripts(workspace: Path, manifests: list[str]) -> dict[str, str]:
    package = next((item for item in manifests if item.casefold().endswith("package.json")), None)
    if package is None:
        return {}
    try:
        payload = json.loads((workspace / package).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    scripts = payload.get("scripts", {})
    return {
        str(key): str(value)
        for key, value in scripts.items()
        if isinstance(key, str) and isinstance(value, str) and value.strip()
    }


def build_ecosystem_profile(
    workspace: Path,
    ecosystem: ProjectEcosystem,
    project_root: str,
    manifests: list[str],
) -> ProjectCapabilityProfile:
    commands: dict[str, ProjectCommand] = {}
    required = ["test"]
    missing: list[str] = []
    source_suffixes: list[str]
    test_patterns: list[str]

    if ecosystem is ProjectEcosystem.PYTHON:
        source_suffixes = [".py"]
        test_patterns = ["test_*.py", "*_test.py", "tests/*.py", "tests/**/*.py"]
        commands = {
            "test": _command([sys.executable, "-m", "pytest"], project_root, accepts_paths=True),
            "build": _command([sys.executable, "-m", "compileall", "."], project_root),
            "lint": _command([sys.executable, "-m", "ruff", "check", "."], project_root),
            "dependency_check": _command([sys.executable, "-m", "pip", "check"], project_root),
            "security_scan": _command(
                [
                    sys.executable,
                    "-m",
                    "ruff",
                    "check",
                    ".",
                    "--select",
                    "S",
                    "--exclude",
                    "tests,test_*.py,*_test.py",
                ],
                project_root,
            ),
        }
    elif ecosystem is ProjectEcosystem.NODE:
        source_suffixes = [".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte"]
        test_patterns = [
            "test/*.js", "test/*.ts", "tests/**/*.js", "tests/**/*.ts",
            "**/*.test.js", "**/*.test.ts", "**/*.spec.js", "**/*.spec.ts",
        ]
        scripts = _node_scripts(workspace, manifests)
        if "test" in scripts and "no test specified" not in scripts["test"].casefold():
            commands["test"] = _command(["npm", "test"], project_root)
        else:
            missing.append("test command is not declared in package.json scripts")
        if "build" in scripts:
            commands["build"] = _command(["npm", "run", "build"], project_root)
            required.append("build")
        if "lint" in scripts:
            commands["lint"] = _command(["npm", "run", "lint"], project_root)
        commands["dependency_check"] = _command(["npm", "ls", "--all"], project_root)
    elif ecosystem is ProjectEcosystem.DOTNET:
        source_suffixes = [".cs", ".fs", ".vb"]
        test_patterns = ["tests/**/*.cs", "tests/**/*.fs", "**/*Tests.cs", "**/*Tests.fs"]
        commands = {
            "test": _command(["dotnet", "test"], project_root),
            "build": _command(["dotnet", "build"], project_root),
            "lint": _command(["dotnet", "format", "--verify-no-changes"], project_root),
        }
        required.append("build")
    elif ecosystem is ProjectEcosystem.JAVA:
        source_suffixes = [".java", ".kt", ".kts"]
        test_patterns = ["src/test/**/*.java", "src/test/**/*.kt", "**/*Test.java", "**/*Test.kt"]
        root = workspace / project_root
        uses_gradle = any(Path(item).name.casefold().startswith("build.gradle") for item in manifests)
        if uses_gradle:
            wrapper = "gradlew.bat" if os.name == "nt" else "./gradlew"
            executable = wrapper if (root / wrapper).exists() else "gradle"
            commands = {
                "test": _command([executable, "test"], project_root),
                "build": _command([executable, "build"], project_root),
            }
        else:
            wrapper = "mvnw.cmd" if os.name == "nt" else "./mvnw"
            executable = wrapper if (root / wrapper).exists() else "mvn"
            commands = {
                "test": _command([executable, "test"], project_root),
                "build": _command([executable, "package", "-DskipTests"], project_root),
            }
        required.append("build")
    elif ecosystem is ProjectEcosystem.GO:
        source_suffixes = [".go"]
        test_patterns = ["*_test.go", "**/*_test.go"]
        commands = {
            "test": _command(["go", "test", "./..."], project_root),
            "build": _command(["go", "build", "./..."], project_root),
            "lint": _command(["go", "vet", "./..."], project_root),
        }
        required.append("build")
    elif ecosystem is ProjectEcosystem.RUST:
        source_suffixes = [".rs"]
        test_patterns = ["tests/**/*.rs", "**/*_test.rs"]
        commands = {
            "test": _command(["cargo", "test"], project_root),
            "build": _command(["cargo", "check"], project_root),
            "lint": _command(["cargo", "clippy", "--", "-D", "warnings"], project_root),
        }
        required.append("build")
    else:
        raise ValueError(f"no adapter for ecosystem: {ecosystem.value}")

    if any(item not in commands for item in required):
        return ProjectCapabilityProfile.create(
            status=ProjectCapabilityStatus.UNSUPPORTED,
            ecosystem=ecosystem,
            project_root=project_root,
            manifests=manifests,
            source_suffixes=source_suffixes,
            test_path_patterns=test_patterns,
            commands={},
            required_capabilities=[],
            missing_capabilities=missing or ["mandatory validation command is unavailable"],
            evidence_references=[],
        )
    return ProjectCapabilityProfile.create(
        status=ProjectCapabilityStatus.SUPPORTED,
        ecosystem=ecosystem,
        project_root=project_root,
        manifests=manifests,
        source_suffixes=source_suffixes,
        test_path_patterns=test_patterns,
        commands=commands,
        required_capabilities=list(dict.fromkeys(required)),
        missing_capabilities=missing,
        evidence_references=[],
    )
