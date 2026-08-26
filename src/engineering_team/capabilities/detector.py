from __future__ import annotations

import fnmatch
import os
from pathlib import Path, PurePosixPath

from engineering_team.contracts.enums import (
    ProjectCapabilityStatus,
    ProjectEcosystem,
)
from engineering_team.contracts.models import ProjectCapabilityProfile

from .adapters import GENERATED_PARTS, build_ecosystem_profile, manifest_ecosystem


def _safe_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root)
            if (
                not path.is_file()
                or path.is_symlink()
                or any(part in GENERATED_PARTS for part in relative.parts)
                or any(part == ".env" or part.startswith(".env.") for part in relative.parts)
            ):
                continue
            files.append(path)
        except OSError:
            continue
    return files


def _project_root(root: Path, manifests: list[Path]) -> str:
    if not manifests:
        return "."
    parents = [str(path.parent) for path in manifests]
    common = Path(os.path.commonpath(parents))
    relative = common.relative_to(root).as_posix()
    return relative or "."


def detect_project_capabilities(root: str | Path) -> ProjectCapabilityProfile:
    workspace = Path(root).resolve()
    files = _safe_files(workspace)
    detected: dict[ProjectEcosystem, list[Path]] = {}
    for path in files:
        ecosystem = manifest_ecosystem(path)
        if ecosystem is not None:
            detected.setdefault(ecosystem, []).append(path)
    if not detected and any(path.suffix.casefold() == ".py" for path in files):
        detected[ProjectEcosystem.PYTHON] = []
    if len(detected) > 1:
        manifests = sorted(
            path.relative_to(workspace).as_posix()
            for paths in detected.values()
            for path in paths
        )
        return ProjectCapabilityProfile.create(
            status=ProjectCapabilityStatus.AMBIGUOUS,
            ecosystem=ProjectEcosystem.UNKNOWN,
            project_root=".",
            manifests=manifests,
            source_suffixes=[],
            test_path_patterns=[],
            commands={},
            required_capabilities=[],
            missing_capabilities=[
                "multiple project ecosystems detected: "
                + ", ".join(sorted(item.value for item in detected))
            ],
            evidence_references=[],
        )
    if not detected:
        return ProjectCapabilityProfile.create(
            status=ProjectCapabilityStatus.UNSUPPORTED,
            ecosystem=ProjectEcosystem.UNKNOWN,
            project_root=".",
            manifests=[],
            source_suffixes=[],
            test_path_patterns=[],
            commands={},
            required_capabilities=[],
            missing_capabilities=["no supported project manifest or source ecosystem detected"],
            evidence_references=[],
        )
    ecosystem, manifest_paths = next(iter(detected.items()))
    manifests = sorted(path.relative_to(workspace).as_posix() for path in manifest_paths)
    return build_ecosystem_profile(
        workspace,
        ecosystem,
        _project_root(workspace, manifest_paths),
        manifests,
    )


def _safe_relative(relative: str) -> str:
    normalized = relative.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
    ):
        raise ValueError("path must be workspace-relative")
    return path.as_posix()


def is_native_test_path(profile: ProjectCapabilityProfile, relative: str) -> bool:
    try:
        normalized = _safe_relative(relative)
    except ValueError:
        return False
    root = profile.project_root.rstrip("/")
    if root not in {"", "."}:
        prefix = root + "/"
        if not normalized.startswith(prefix):
            return False
        normalized = normalized[len(prefix):]
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in profile.test_path_patterns)


def command_for(
    profile: ProjectCapabilityProfile,
    capability: str,
    paths: list[str] | None = None,
) -> list[str] | None:
    command = profile.commands.get(capability)
    if command is None:
        return None
    argv = list(command.argv)
    if not paths or not command.accepts_paths:
        return argv
    for relative in paths:
        if capability == "test" and not is_native_test_path(profile, relative):
            raise ValueError(f"not a native test path: {relative}")
        normalized = _safe_relative(relative)
        root = profile.project_root.rstrip("/")
        if root not in {"", "."}:
            normalized = normalized.removeprefix(root + "/")
        argv.append(normalized)
    return argv
