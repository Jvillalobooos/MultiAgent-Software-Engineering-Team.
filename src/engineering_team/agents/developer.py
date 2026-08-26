import ast
import re
from pathlib import PurePosixPath
from typing import Any, ClassVar

from engineering_team.contracts.enums import ActionMode, ToolStatus
from engineering_team.contracts.models import ImplementationResult
from engineering_team.models.context import ContextEnvelope

from .base import AgentBase

DEVELOPER_EDITABLE_SOURCE_CHARS = 4_000


class DeveloperAgent(AgentBase[ImplementationResult]):
    role = "Developer"
    _MAX_EDITABLE_SOURCE_CHARS = DEVELOPER_EDITABLE_SOURCE_CHARS
    _GENERATED_PARTS: ClassVar[set[str]] = {
        "workspace", "evaluation", "traces", "rag", "chroma", "__pycache__",
        ".pytest_cache", ".ruff_cache", ".git", ".venv", "node_modules",
        "dist", "build", "coverage", "htmlcov",
    }
    _SOURCE_SUFFIXES: ClassVar[set[str]] = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb",
        ".php", ".cs", ".c", ".h", ".cpp", ".hpp", ".swift", ".kt", ".kts",
        ".scala", ".vue", ".svelte",
    }
    _PROJECT_FILES: ClassVar[set[str]] = {
        "pyproject.toml", "package.json", "tsconfig.json", "cargo.toml", "go.mod",
        "pom.xml", "build.gradle", "build.gradle.kts", "composer.json", "gemfile",
    }
    # Generic package/index markers that carry little standalone information.
    # Weak signal only: real structural evidence always outranks this penalty.
    _LOW_INFO_STEMS: ClassVar[set[str]] = {"__init__", "index", "mod", "package-info"}
    # Generic cross-language architecture-role tokens used only as a weak scoring
    # signal; never required and never sufficient on their own.
    _ROLE_HINTS: ClassVar[set[str]] = {
        "service", "controller", "domain", "repository", "handler",
        "usecase", "manager", "logic", "model",
    }
    _IMPORT_PATTERNS: ClassVar[tuple[re.Pattern[str], ...]] = (
        re.compile(r"(?m)^\s*from\s+([.\w]+)\s+import\b"),
        re.compile(r"(?m)^\s*import\s+(?:static\s+)?([.\w]+)\s*;?"),
        re.compile(r"""import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]"""),
        re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
    )

    _STOP_WORDS: ClassVar[set[str]] = {
        "after", "allow", "authorized", "belonging", "bounded", "change",
        "exactly", "from", "latest", "only", "provide", "return", "safe",
        "that", "their", "this", "using", "with",
    }

    @staticmethod
    def _python_boundaries(content: str) -> set[str]:
        tree = ast.parse(content)
        boundaries: set[str] = set()
        route_decorators = {
            "get", "post", "put", "patch", "delete", "route", "api_route",
        }
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                boundaries.add(f"class:{node.name}")
                continue
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_route = False
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = (
                    target.attr
                    if isinstance(target, ast.Attribute)
                    else target.id if isinstance(target, ast.Name) else ""
                )
                is_route |= name in route_decorators
            prefix = "route" if is_route else "function"
            boundaries.add(f"{prefix}:{node.name}")
        return boundaries

    @classmethod
    def validate_update_preservation(
        cls,
        path: str,
        original: str,
        proposed: str,
        removal_basis: str = "",
    ) -> tuple[bool, list[str]]:
        """Fail closed unless removal of a Python boundary is explicitly authorized."""
        if PurePosixPath(path.replace("\\", "/")).suffix.casefold() != ".py":
            return True, []
        try:
            original_boundaries = cls._python_boundaries(original)
            proposed_boundaries = cls._python_boundaries(proposed)
        except SyntaxError:
            return False, ["python-ast:unparseable-update"]
        removed = sorted(original_boundaries - proposed_boundaries)
        basis = " ".join(removal_basis.casefold().split())
        removal_action = r"(?:remove|delete|retire|deprecat\w*|replace)"
        unauthorized = []
        for boundary in removed:
            name = re.escape(boundary.partition(":")[2].casefold())
            explicitly_authorized = bool(
                re.search(rf"{removal_action}.{{0,80}}\b{name}\b", basis)
                or re.search(rf"\b{name}\b.{{0,80}}{removal_action}", basis)
            )
            if not explicitly_authorized:
                unauthorized.append(boundary)
        return not unauthorized, unauthorized

    @classmethod
    def relevance_terms(cls, specification: Any, architecture: Any, requirement: str) -> list[str]:
        values = [
            requirement,
            getattr(specification, "objective", ""),
            " ".join(getattr(specification, "business_rules", [])),
            " ".join(getattr(architecture, "components", [])),
            " ".join(getattr(architecture, "apis", [])),
            " ".join(getattr(architecture, "data_changes", [])),
        ]
        terms: list[str] = []
        for token in re.findall(r"[A-Za-z_][A-Za-z0-9_/-]*", " ".join(values).lower()):
            normalized = token.strip("/_-")
            if len(normalized) >= 4 and normalized not in cls._STOP_WORDS:
                terms.append(normalized)
        return list(dict.fromkeys(terms))

    @classmethod
    def rank_paths(
        cls,
        paths: list[str],
        search_hits: list[str],
        terms: list[str],
        structural_boost: set[str] | None = None,
    ) -> list[str]:
        """Deterministically order candidates: structural evidence first, then
        search/requirement signals, then weak generic role hints. Information
        value -- never file length -- breaks ties, so a short package marker
        cannot outrank a real implementation module."""
        structural_boost = structural_boost or set()
        hit_counts = {path: search_hits.count(path) for path in paths}

        def score(path: str) -> int:
            folded = path.casefold()
            stem = PurePosixPath(path).stem.casefold()
            term_score = sum(term in folded for term in terms)
            source_score = hit_counts[path]
            code_score = 1 if PurePosixPath(path).suffix in {".py", ".js", ".ts", ".java"} else 0
            role_score = 1 if any(hint in stem for hint in cls._ROLE_HINTS) else 0
            low_info_penalty = 1 if stem in cls._LOW_INFO_STEMS else 0
            structural_score = 5 if path in structural_boost else 0
            return (
                structural_score * 20
                + source_score * 10
                + term_score * 4
                + role_score
                - low_info_penalty * 3
                + code_score
            )

        return sorted(paths, key=lambda path: (-score(path), path))

    @staticmethod
    def _safe_path(path: str) -> bool:
        candidate = PurePosixPath(path.replace("\\", "/"))
        return bool(
            path
            and not candidate.is_absolute()
            and ".." not in candidate.parts
            and not any(part == ".env" or part.startswith(".env.") for part in candidate.parts)
            and "__pycache__" not in candidate.parts
        )

    @classmethod
    def is_implementation_candidate(cls, path: str) -> bool:
        """Separate sandbox-safe paths from files suitable for a bounded code change."""
        if not cls._safe_path(path):
            return False
        candidate = PurePosixPath(path.replace("\\", "/"))
        parts = {part.casefold() for part in candidate.parts}
        if parts & cls._GENERATED_PARTS:
            return False
        return candidate.suffix.casefold() in cls._SOURCE_SUFFIXES or candidate.name.casefold() in cls._PROJECT_FILES

    @classmethod
    def structural_references(
        cls, content: str, source_path: str, candidate_paths: list[str]
    ) -> list[str]:
        """Return repository-local candidates that source_path's imports/references
        point to, using a bounded conservative heuristic (no compiler/parser).

        Supports common relative/absolute import syntaxes (Python, JS/TS, Java-like
        dotted imports) and falls back to filename/basename matching when the exact
        syntax is not recognized. Only ever returns paths already present in
        candidate_paths, so it can never surface a generated, sandbox-unsafe, or
        otherwise disqualified path.
        """
        candidates = set(candidate_paths)
        raw_refs: list[str] = []
        for pattern in cls._IMPORT_PATTERNS:
            raw_refs.extend(pattern.findall(content))
        references: list[str] = []
        seen: set[str] = set()
        for raw in raw_refs:
            resolved = cls._resolve_reference(raw, source_path, candidates)
            if resolved and resolved != source_path and resolved not in seen:
                seen.add(resolved)
                references.append(resolved)
        return references

    @classmethod
    def _resolve_reference(cls, raw: str, source_path: str, candidates: set[str]) -> str | None:
        ref = raw.strip()
        if not ref:
            return None
        source_dir = PurePosixPath(source_path).parent
        if ref.startswith(("./", "../")):
            directory = source_dir
            remainder = ref
            while remainder.startswith("../"):
                directory = directory.parent
                remainder = remainder[3:]
            remainder = remainder.removeprefix("./")
            base = directory / remainder if remainder else directory
            return cls._match_basename(base, candidates)
        if ref.startswith("."):
            dots = len(ref) - len(ref.lstrip("."))
            module = ref[dots:]
            directory = source_dir
            for _ in range(dots - 1):
                directory = directory.parent
            parts = [part for part in module.split(".") if part]
            base = directory
            for part in parts:
                base = base / part
            return cls._match_basename(base, candidates)
        parts = [part for part in ref.replace("/", ".").split(".") if part]
        if not parts:
            return None
        match = cls._match_basename(PurePosixPath(*parts), candidates)
        if match:
            return match
        # Dotted package path (e.g. Java-like) with an unknown source root:
        # fall back to matching the referenced class/module name by basename.
        # Fail closed on ambiguity -- a tail match is only trustworthy when it
        # is the single candidate; two same-named classes in different
        # packages must not be resolved by set-iteration order.
        tail = parts[-1]
        tail_matches = {
            candidate for candidate in candidates
            if PurePosixPath(candidate).stem == tail
            and PurePosixPath(candidate).stem.casefold() not in cls._LOW_INFO_STEMS
        }
        return next(iter(tail_matches)) if len(tail_matches) == 1 else None

    @classmethod
    def _match_basename(cls, base: PurePosixPath, candidates: set[str]) -> str | None:
        base_str = base.as_posix().lstrip("/")
        if base_str in candidates:
            return base_str
        # Collect every suffix/marker variant that exists before deciding: if
        # more than one distinct file could satisfy the same logical
        # reference (e.g. foo.js and foo.ts both present), that is ambiguous
        # and must fail closed rather than pick by set-iteration order.
        matches: set[str] = set()
        for suffix in cls._SOURCE_SUFFIXES:
            direct = f"{base_str}{suffix}"
            if direct in candidates:
                matches.add(direct)
            for marker in ("__init__", "index", "mod"):
                nested = f"{base_str}/{marker}{suffix}"
                if nested in candidates:
                    matches.add(nested)
        return next(iter(matches)) if len(matches) == 1 else None

    @staticmethod
    def _symbols(content: str) -> list[str]:
        patterns = (
            r"(?m)^\s*(?:async\s+)?def\s+([A-Za-z_]\w*\s*\([^)]*\))",
            r"(?m)^\s*class\s+([A-Za-z_]\w*)",
        )
        symbols = [match for pattern in patterns for match in re.findall(pattern, content)]
        return list(dict.fromkeys(symbols))[:6]

    def execute(self, envelope: ContextEnvelope) -> ImplementationResult:
        specification = envelope.state_projection.get("specification")
        architecture = envelope.state_projection.get("architecture")
        repository_results = [
            item for item in envelope.tool_results
            if item.tool_name in {"list_files", "read_file", "search_code", "get_file_content"}
        ]
        listed_paths: list[str] = []
        search_hits: list[str] = []
        inspected_content: dict[str, str] = {}
        for item in repository_results:
            if item.status is not ToolStatus.SUCCESS:
                continue
            if item.tool_name == "list_files":
                listed_paths.extend(
                    line.strip().replace("\\", "/") for line in item.output_summary.splitlines()
                )
            elif item.tool_name == "search_code":
                search_hits.extend(
                    line.strip().replace("\\", "/") for line in item.output_summary.splitlines()
                )
            elif item.tool_name in {"read_file", "get_file_content"}:
                prefix = "path="
                if item.input_summary.startswith(prefix):
                    path = item.input_summary[len(prefix):].replace("\\", "/")
                    if self._safe_path(path):
                        inspected_content[path] = item.output_summary
        safe_listed = list(dict.fromkeys(
            path for path in listed_paths if self.is_implementation_candidate(path)
        ))
        terms = self.relevance_terms(
            specification, architecture, str(envelope.state_projection.get("requirement", ""))
        )
        structural_boost: set[str] = set()
        for src_path, content in inspected_content.items():
            structural_boost.update(
                self.structural_references(content, src_path, safe_listed + list(inspected_content))
            )
        ranked_paths = self.rank_paths(safe_listed, search_hits, terms, structural_boost=structural_boost)
        inspected_paths = [
            path for path in ranked_paths
            if path in inspected_content and len(inspected_content[path]) <= self._MAX_EDITABLE_SOURCE_CHARS
        ]
        search_hit_paths = set(search_hits)
        relevant_inspected = [
            path for path in inspected_paths
            if path in search_hit_paths
            or any(term in path.casefold() or term in inspected_content[path].casefold() for term in terms)
        ]
        if relevant_inspected:
            inspected_paths = relevant_inspected
        evidence = list(dict.fromkeys(
            (
                f"{item.evidence_reference}#{item.input_summary[5:]}"
                if item.evidence_reference
                and item.tool_name in {"read_file", "get_file_content"}
                and item.input_summary.startswith("path=")
                else item.evidence_reference or f"repository:{item.tool_name}"
            )
            for item in repository_results
        ))
        if not inspected_paths:
            return ImplementationResult(
                action_mode=ActionMode.PROPOSED,
                changed_files=[],
                diff=(
                    "NO-OP: repository inspection returned no relevant readable file; "
                    "implementation requires bounded search_code/read_file evidence."
                ),
                evidence=evidence or ["repository inspection returned no safe paths"],
                validation_result=(
                    "NO-OP validation: no proposal can be applied until Repository MCP "
                    "returns a relevant inspected file."
                ),
                security_surface_changed=False,
            )

        components = ", ".join(getattr(architecture, "components", [])) or "current component"
        apis = ", ".join(getattr(architecture, "apis", [])) or "no API change declared"
        data_changes = (
            ", ".join(getattr(architecture, "data_changes", []))
            or "no data change declared"
        )
        decisions = "; ".join(getattr(architecture, "decisions", [])) or "preserve design"
        objective = getattr(specification, "objective", envelope.current_task)
        changed_files = inspected_paths[:2]
        proposal = [
            "PROPOSED TECHNICAL CHANGE",
            f"Objective: {objective}",
            f"Components: {components}",
            f"APIs: {apis}",
            f"Data: {data_changes}",
            f"Design decisions: {decisions}",
        ]
        for path in changed_files:
            symbols = self._symbols(inspected_content[path])
            target = ", ".join(symbols) if symbols else "the inspected module boundary"
            proposal.extend([
                f"FILE: {path}",
                f"Observed symbols: {target}",
                f"Technical change: adapt {target} to satisfy {objective}.",
                f"API implications: {apis}.",
                f"Data implications: {data_changes}.",
                f"--- a/{path}",
                f"+++ b/{path}",
                "@@ proposed @@",
                f"+ Update {target} while preserving: {decisions}.",
            ])
        security_terms = " ".join((
            getattr(specification, "source_requirement", ""),
            " ".join(getattr(architecture, "apis", [])),
            " ".join(getattr(architecture, "data_changes", [])),
            " ".join(getattr(architecture, "risks", [])),
            *(inspected_content[path] for path in changed_files),
        )).lower()
        return ImplementationResult(
            action_mode=ActionMode.PROPOSED,
            changed_files=changed_files,
            diff="\n".join(proposal),
            evidence=evidence or [f"repository:list_files:{path}" for path in changed_files],
            validation_result=(
                "PROPOSED validation strategy: run_build, run_linter, and run_tests in the "
                f"isolated workspace after applying changes to {len(changed_files)} inspected path(s)."
            ),
            security_surface_changed=any(
                term in security_terms
                for term in ("api", "auth", "owner", "security", "token", "password", "idor")
            ),
        )
