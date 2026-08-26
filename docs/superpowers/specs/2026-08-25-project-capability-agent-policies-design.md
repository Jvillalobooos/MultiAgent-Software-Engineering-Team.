# Project Capability and Agent Policy Design

## Purpose

Make the governed engineering workflow operate from repository evidence across
supported project ecosystems instead of assuming Python, pytest, English
requirements, or a particular UI/API shape. All six agents must receive
consistent instructions about facts they must preserve, fields they may enrich,
and capabilities the target project actually exposes.

The workflow remains fail-closed. An unknown ecosystem, ambiguous executable
root, absent mandatory test command, unavailable required tool, or insufficient
inspected context produces `INCOMPLETE` with evidence. It never causes an
invented command, path, dependency, framework, or successful validation.

## Scope

The first implementation supports these ecosystems when their identifying
files are present:

| Ecosystem | Evidence |
| --- | --- |
| Python | `pyproject.toml`, `pytest.ini`, `setup.cfg`, `setup.py`, or Python source |
| Node/TypeScript | `package.json`, optionally `tsconfig.json` |
| .NET | `.sln`, `.csproj`, or `.fsproj` |
| Java | `pom.xml`, `build.gradle`, `build.gradle.kts`, or wrapper files |
| Go | `go.mod` |
| Rust | `Cargo.toml` |

Repositories may contain more than one ecosystem. Detection selects one
primary project root only when the requirement-relevant inspected paths and a
manifest agree. Otherwise the profile is `AMBIGUOUS` and the run ends safely.
Framework-specific business behavior remains model-driven and evidence-bound;
the detector identifies capabilities, not product intent.

## Architecture

### Project capability profile

Add a strict `ProjectCapabilityProfile` contract and a typed
`project_capabilities` field to `EngineeringState`/`WorkflowState`. It contains:

- `status`: `SUPPORTED`, `AMBIGUOUS`, or `UNSUPPORTED`;
- `ecosystem`: `python`, `node`, `dotnet`, `java`, `go`, `rust`, or `unknown`;
- `project_root`: a workspace-relative directory;
- `manifests`: inspected workspace-relative manifest paths;
- `source_suffixes` and `test_path_patterns`;
- optional argv arrays for `test`, `build`, `lint`, `dependency_check`, and
  `security_scan`;
- `required_capabilities`: validation capabilities the delivery gate requires;
- `missing_capabilities`: explicit reasons a command could not be derived;
- `evidence_references`: Repository MCP references used to derive the profile.
- `fingerprint`: SHA-256 over the canonical profile excluding evidence
  references and the fingerprint itself.

Commands are argv arrays, never shell strings. A command may come only from a
checked-in manifest/script or a fixed ecosystem adapter. Detection never reads
environment secrets, traverses outside the isolated workspace, downloads a
tool, or executes during profiling.

Create `engineering_team.project_capabilities` with one pure deterministic
detector and focused adapters. The detector handles manifest discovery, root
selection, and ambiguity. Each adapter owns suffixes, test conventions, and
safe command derivation for one ecosystem.

Repository MCP exposes `detect_project_capabilities` to a deterministic
`ProjectCapabilities` graph node placed between `START` and Product. The node
uses Architecture's existing read authorization; Product itself still invokes
no repository tool. The call returns a normal `ToolResult` whose
`output_summary` is canonical profile JSON and whose evidence reference
identifies the MCP call. The graph validates that JSON as
`ProjectCapabilityProfile` before placing it in state. A malformed result is
`MCP_ERROR`, never partially accepted.

### Quality MCP execution

Quality MCP invokes the same pure detector inside its own server process. Each
quality call receives only the expected profile fingerprint. The server
re-detects the workspace, rejects a fingerprint mismatch, and executes argv
from its locally derived profile with
`subprocess.run(..., shell=False, cwd=project_root)`. The graph or model never
sends an executable or argv across MCP. Existing role authorization, timeout,
output bounding, and `ToolResult` behavior remain.

The fixed Python commands become the Python adapter rather than global
defaults. Node scripts are used only when declared in `package.json`; Java
prefers checked-in Maven or Gradle wrappers; other adapters use installed
ecosystem CLIs. A missing executable is `UNAVAILABLE`. A non-zero command is
`FAIL`. Neither is converted into success or silently replaced with Python.

Every supported implementation requires a test capability. Build is also
required for compiled ecosystems and when a checked-in Node build script is
declared. Lint, dependency, and security commands are executed when safely
derivable; their absence is recorded in the profile but does not masquerade as
a failed execution. The delivery gate requires successful evidence for every
item in `required_capabilities`.

When a test runner accepts safe relative file arguments, its adapter appends
validated generated-test paths. Otherwise it runs the complete native suite.
Testing never appends a path using another ecosystem's syntax.

### Central agent field policies

Add one role policy registry used by prompt construction and semantic
validation. Each policy names exact preserved fields, additive-list fields,
enrichable fields, permitted mutation fields, and evidence fields. Prompts are
generated from this registry so they cannot contradict `_preserves_governed_facts`.

- Product preserves `source_requirement` and every explicit deterministic
  rule. It may add actors, ambiguities, assumptions, acceptance criteria, and
  non-functional requirements grounded in the supplied text and capability
  profile.
- Architecture preserves evidence provenance and known risks. It may describe
  components, APIs, data changes, dependencies, decisions, and impact only when
  supported by Product facts and the profile.
- Developer returns only bounded mutations for inspected safe paths. It does
  not infer UI, API, persistence, authentication, or another architectural
  surface unless the requirement, Architecture artifact, or inspected files
  contain evidence for it.
- Security may add findings and recommendations but cannot weaken deterministic
  status, severity, failed checklist controls, scan failures, or provenance.
- Testing may add ecosystem-native test mutations only under validated test
  paths. It cannot change production files, erase failures, claim unexecuted
  results, or substitute another ecosystem's test framework.
- Reviewer may explain and score validated evidence but cannot weaken status,
  problems, return recommendation, or evidence references. Graph routing and
  final approval remain deterministic.

### Requirement interpretation

Product identifies ambiguities without translating a word into a technical
surface. Developer receives a general evidence rule: generic natural-language
terms such as “way”, “form”, “method”, or equivalents in any language do not
mean graphical form, endpoint, database, or CLI by themselves. The smallest
change must be selected from explicit requirement facts, Architecture output,
the capability profile, and inspected repository structure.

No language-specific keyword table decides product behavior. Regression
fixtures may use Spanish and English to prove the evidence rule, but production
logic remains language-neutral.

### Context selection and remediation

Replace “last two read results” with deterministic bounded selection:

1. retain successfully inspected paths targeted by the current candidate;
2. retain a referenced structural neighbor when it supplies the implementation
   boundary;
3. include a newly discovered remediation path only when it outranks an
   existing path by requirement terms, manifest proximity, or import/reference
   evidence;
4. exclude generated directories, secrets, binary files, unsupported suffixes,
   oversized files, and low-information package markers unless structurally
   required.

The prompt still includes at most two complete editable files, each bounded at
4,000 characters. Remediation may change one slot but cannot discard every
previously relevant implementation path. The chosen paths and ranking reasons
are recorded in trace metadata.

Testing receives the implementation diff, capability profile, and at most one
inspected native test example. Repository MCP grants Testing read-only access
through a dedicated `read_test_file` tool. That tool re-detects the profile,
verifies the expected fingerprint, and accepts only paths matched by its
validated native test patterns; its existing write restriction to test paths
remains and is changed to use the same patterns.

Generation budgets are role-specific and derived from their bounded mutable
payloads. Developer and Testing receive enough output for their maximum
complete-file mutation contracts; Product, Architecture, Security, and
Reviewer retain smaller artifact-only bounds. Every budget has a regression
test against its schema contract.

## Workflow

1. The isolated workspace is created.
2. `ProjectCapabilities` asks Repository MCP to inspect safe candidate
   manifests.
3. Repository MCP detection produces profile JSON plus provenance; the graph
   validates it and stores the typed profile.
4. If the profile is unsupported or ambiguous, the graph records a typed
   capability error and terminates `INCOMPLETE` before model-driven mutation.
5. Product and Architecture receive the profile and produce governed enriched
   artifacts.
6. Developer inspection uses the profile's suffixes and deterministic ranking.
7. A validated mutation plan is applied only through Repository MCP; real
   writes and `get_diff` establish `APPLIED`.
8. Security invokes only supported profile commands after Quality MCP verifies
   the profile fingerprint, then evaluates the diff, RAG, and tool evidence.
9. Testing inspects a native test example when available, writes native tests,
   and Quality MCP verifies the fingerprint before running its locally derived
   test command.
10. Reviewer applies the existing delivery gates. Approval still requires an
    applied implementation, non-empty diff, requirement-specific generated
    tests, successful validation, and no unresolved required-evidence error.

## Errors and observability

Add a typed `PROJECT_CAPABILITY_ERROR` workflow error for unsupported,
ambiguous, or mandatory-capability-missing profiles. Its detail lists the
manifests considered, selected/ambiguous roots, missing capability, and safe
next action. Reports include a sanitized profile summary.

Structured-response repair remains stateless and self-contained for every
role. A failed attempt with a remaining local repair is a Langfuse `WARNING`;
the exhausted attempt is `ERROR`. Langfuse authentication or HTTP
unavailability degrades to the correlated local trace and cannot abort the
workflow. Profile detection, selected context paths, argv commands, tool exit
status, and terminal capability decisions are trace events with secrets
redacted.

## Testing

### Unit coverage

- table-driven profile fixtures for Python, Node/TypeScript, .NET, Maven,
  Gradle, Go, Rust, hybrid ambiguity, and unknown projects;
- argv derivation, relative root selection, manifest evidence, secret/path
  rejection, and missing executable classification;
- each of the six role policies against allowed enrichment and prohibited fact
  weakening;
- context retention across remediation and exclusion of oversized or
  low-information files;
- language-neutral ambiguity behavior with Spanish and English fixtures;
- native test path validation for every supported adapter.

### Integration coverage

- Python and Node minimal workspaces complete with their native test commands;
- one compiled ecosystem fixture validates build/test command routing;
- unknown and ambiguous workspaces finish `INCOMPLETE` without invoking a
  mutation model or subprocess command;
- Testing cannot read or write production paths;
- Langfuse connectivity failure and structured repair remain non-fatal when
  recovery is available;
- existing security, retry, remediation, and maximum-iteration tests remain
  green.

### Functional verification

Run the real Spanish password-change requirement against `sample_app` with
cached local models. Success requires `APPROVED`, at least one Repository MCP
write, a non-empty diff, a generated native test, successful Quality MCP
validation, six final valid role executions, and no Langfuse `ERROR` event.
The full pytest suite, Ruff, `git diff --check`, and report/trace inspection are
required before completion is claimed.

## Compatibility and rollout

The CLI and `--project` interface do not change. Existing Python behavior is
migrated into the Python adapter first, retaining current commands and tests.
Other adapters are enabled only after their fixtures pass. No dependency is
added and no external package is installed automatically.

Existing serialized states without a profile are accepted by deriving one at
the start of the run. Existing model and tool evidence remains append-only.
The old fixed Python Quality MCP behavior is removed only after the Python
adapter integration tests prove equivalent results.

## Non-goals

- Claiming support for every possible language or build system.
- Downloading SDKs, package managers, linters, scanners, or test runners.
- Guessing commands for unknown manifests.
- Allowing models to select routes, providers, commands, or authorization.
- Replacing deterministic approval gates with model confidence.
