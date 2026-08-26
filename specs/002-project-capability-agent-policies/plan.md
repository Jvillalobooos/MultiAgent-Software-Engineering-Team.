# Project Capability and Agent Policies Implementation Plan

**Goal:** Generalize the governed six-agent workflow across supported project
ecosystems while preserving safe `INCOMPLETE` outcomes for unknown or ambiguous
projects.

**Architecture:** A deterministic capability detector produces a strict,
fingerprinted project profile before Product runs. Repository and Quality MCP
derive the profile independently, agent prompts use one central preservation
policy registry, Developer context remains relevant across remediation, and
Testing creates and executes only ecosystem-native tests.

**Tech Stack:** Python 3.10+, Pydantic v2, LangGraph, MCP stdio, HTTPX/Ollama,
Langfuse v4, pytest, Ruff.

**Spec:** `specs/002-project-capability-agent-policies/spec.md`

## Global constraints

- Use TDD for every behavior change: add one failing test, verify its expected
  failure, implement the minimum behavior, then verify focused and regression
  tests.
- Models never choose routes, executable commands, project roots, permissions,
  providers, or evidence.
- Commands are derived inside the Quality MCP server and executed with
  `shell=False`; only a profile fingerprint crosses from the graph.
- Unknown, ambiguous, or mandatory-capability-missing projects terminate
  `INCOMPLETE` without model mutation or subprocess execution.
- Existing user changes under `evaluation/reports/` remain untouched and are
  never staged by this work.
- The source project remains immutable; all writes stay in the run workspace.

---

## Phase 1 — Existing failure recovery

### Task 1: Structured-output and Langfuse recovery

**Files:**
- Modify: `src/engineering_team/agents/developer.py`
- Modify: `src/engineering_team/llm/runtime.py`
- Modify: `src/engineering_team/observability/langfuse.py`
- Modify: `tests/unit/test_model_runtime.py`
- Modify: `tests/integration/test_observability.py`
- Modify: `docs/evaluation.md`

**Interfaces:**
- `DEVELOPER_EDITABLE_SOURCE_CHARS: int = 4_000`
- `DEVELOPER_OUTPUT_TOKEN_LIMIT: int = 4_096`
- `LocalModelRuntime._record(..., level: str | None = None) -> None`
- `LangfuseTracer.start_run(...) -> TraceSession`

- [x] Add RED tests for complete bounded Developer context, self-contained
  invalid-JSON repair, recovered warning severity, exhausted error severity,
  output budget, and Langfuse connection fallback.
- [x] Include complete editable source, embed the invalid response as untrusted
  repair data, and trace only exhausted attempts as `ERROR`.
- [x] Catch `httpx.HTTPError` during Langfuse authentication and degrade to a
  local correlated trace.
- [x] Verify model-runtime and observability tests.

## Phase 2 — Capability contracts and deterministic detection

### Task 2: Strict capability contracts

**Files:**
- Modify: `src/engineering_team/contracts/enums.py`
- Modify: `src/engineering_team/contracts/models.py`
- Modify: `src/engineering_team/contracts/state.py`
- Test: `tests/unit/test_project_capabilities.py`

**Interfaces:**
- `ProjectCapabilityStatus`: `SUPPORTED | AMBIGUOUS | UNSUPPORTED`
- `ProjectEcosystem`: `python | node | dotnet | java | go | rust | unknown`
- `ProjectCommand(argv: list[str], accepts_paths: bool, cwd: str)`
- `ProjectCapabilityProfile(..., fingerprint: str)`
- `EngineeringState.project_capabilities: ProjectCapabilityProfile | None`

- [ ] Write RED validation tests for empty argv, absolute/outside `cwd`, unknown
  commands on supported profiles, and fingerprint mismatch.
- [ ] Implement strict models and canonical SHA-256 fingerprint validation.
- [ ] Run `pytest tests/unit/test_project_capabilities.py -q`.

### Task 3: Ecosystem adapters and detector

**Files:**
- Create: `src/engineering_team/capabilities/__init__.py`
- Create: `src/engineering_team/capabilities/adapters.py`
- Create: `src/engineering_team/capabilities/detector.py`
- Test: `tests/unit/test_project_capabilities.py`

**Interfaces:**
- `detect_project_capabilities(root: str | Path) -> ProjectCapabilityProfile`
- `is_native_test_path(profile, relative: str) -> bool`
- `command_for(profile, capability: str, paths: list[str] | None = None) -> list[str] | None`

- [ ] Add table-driven RED fixtures for Python source fallback,
  Node/TypeScript scripts, .NET, Maven/Gradle, Go, Rust, hybrid ambiguity, and
  unknown projects.
- [ ] Implement adapter constants and safe manifest parsing; derive argv arrays
  without executing or downloading anything.
- [ ] Add RED tests for secret/generated directory exclusion, native test path
  matching, path-argument runners, and full-suite-only runners.
- [ ] Implement path validation and command derivation.
- [ ] Run the capability unit suite.

## Phase 3 — MCP capability boundary

### Task 4: Repository MCP capability evidence

**Files:**
- Modify: `src/engineering_team/mcp/repository.py`
- Modify: `src/engineering_team/mcp/server.py`
- Modify: `src/engineering_team/mcp/client.py`
- Modify: `tests/mcp/test_repository.py`
- Modify: `tests/mcp/test_protocol.py`

**Interfaces:**
- `RepositoryMCP.detect_project_capabilities(role) -> ToolResult`
- `MCPRepositoryClient.detect_project_capabilities(role) -> ToolResult`
- `RepositoryMCP.read_test_file(role, relative, profile_fingerprint) -> ToolResult`

- [ ] Write RED direct and stdio tests for canonical profile JSON/provenance and
  Testing read denial outside native test paths.
- [ ] Expose detector/read-test tools with existing role and path guards.
- [ ] Verify direct and protocol repository tests.

### Task 5: Profile-driven Quality MCP

**Files:**
- Modify: `src/engineering_team/mcp/quality.py`
- Modify: `src/engineering_team/mcp/server.py`
- Modify: `src/engineering_team/mcp/client.py`
- Modify: `tests/mcp/test_quality.py`
- Modify: `tests/mcp/test_protocol.py`

**Interfaces:**
- All Quality methods accept `profile_fingerprint: str | None = None`.
- Quality re-detects locally and rejects mismatched fingerprints.
- `run_tests(..., paths=None, profile_fingerprint=None) -> ToolResult`

- [ ] Add RED tests proving Python uses pytest, Node uses only declared npm
  scripts, compiled ecosystems use native build/test argv, and unknown or
  mismatched profiles execute no subprocess.
- [ ] Replace global Python commands with profile command lookup while keeping
  authorization, timeout, bounded output, and `shell=False`.
- [ ] Verify direct and real stdio Quality MCP tests.

## Phase 4 — Graph and context integration

### Task 6: ProjectCapabilities graph node

**Files:**
- Modify: `src/engineering_team/graph/stategraph.py`
- Modify: `src/engineering_team/contracts/enums.py`
- Modify: `src/engineering_team/models/context.py`
- Modify: `tests/integration/test_workflow.py`
- Modify: `tests/unit/test_context.py`

**Interfaces:**
- `WorkflowState.project_capabilities`
- `ErrorCode.PROJECT_CAPABILITY_ERROR`
- Graph edge `START -> ProjectCapabilities -> Product|INCOMPLETE`

- [ ] Add RED tests that supported profiles reach Product and all six context
  projections, while ambiguous/unknown/missing-test profiles stop before the
  first model call with sanitized diagnostics.
- [ ] Implement the deterministic node, validation, tracing, report evidence,
  and backward-compatible no-adapter behavior for isolated graph unit tests.
- [ ] Pass the profile fingerprint to every Quality MCP call.
- [ ] Verify context and workflow tests.

## Phase 5 — Consistent six-agent policies

### Task 7: Central field-policy registry

**Files:**
- Create: `src/engineering_team/llm/policies.py`
- Modify: `src/engineering_team/llm/runtime.py`
- Modify: `src/engineering_team/prompts/*/system.md`
- Modify: `tests/unit/test_model_runtime.py`
- Modify: `tests/unit/test_prompts.py`

**Interfaces:**
- `ArtifactPolicy(exact_fields, additive_fields, enrichable_fields, mutation_fields)`
- `policy_for(role: AgentRole, artifact_type: type[BaseModel]) -> ArtifactPolicy`
- `preserves_governed_facts(candidate, parsed, policy) -> bool`

- [ ] Add RED parameterized tests for allowed enrichment and prohibited
  weakening for Product, Architecture, Developer, Security, Testing, Reviewer.
- [ ] Implement the registry and generate prompt instructions from the same
  policy used by semantic validation.
- [ ] Remove the contradictory global “copy every value exactly” instruction
  where enrichment is authorized.
- [ ] Verify prompt and runtime tests.

### Task 8: Evidence-based intent and remediation context

**Files:**
- Modify: `src/engineering_team/llm/runtime.py`
- Modify: `src/engineering_team/agents/developer.py`
- Modify: `src/engineering_team/prompts/developer/system.md`
- Modify: `tests/unit/test_developer_agent.py`
- Modify: `tests/unit/test_model_runtime.py`
- Modify: `tests/integration/test_workflow.py`

**Interfaces:**
- Developer `_invoke_schema` receives preferred inspected paths from the
  deterministic `ImplementationResult`.
- Prompt selection returns at most two complete bounded source files plus trace
  metadata describing selection.

- [ ] Add RED tests that a generic natural-language “way/form/method” does not
  imply UI without repository evidence and that remediation retains a relevant
  service path while admitting one stronger new path.
- [ ] Implement language-neutral evidence instructions and deterministic
  preferred-path selection; remove latest-read ordering.
- [ ] Verify Developer and workflow regressions.

## Phase 6 — Ecosystem-native Testing

### Task 9: Native test planning and guarded test context

**Files:**
- Modify: `src/engineering_team/agents/testing.py`
- Modify: `src/engineering_team/llm/runtime.py`
- Modify: `src/engineering_team/graph/stategraph.py`
- Modify: `src/engineering_team/prompts/testing/system.md`
- Modify: `tests/unit/test_agents.py`
- Modify: `tests/unit/test_model_runtime.py`
- Modify: `tests/integration/test_workflow.py`

**Interfaces:**
- `TestingMutationPlan(test_mutations: list[FileMutation], no_mutation_reason: str | None)`
- Testing may read one validated native test example and write only a profile
  native test path.

- [ ] Add RED Python and Node tests proving generated paths/content are native,
  production reads/writes are denied, duplicate normalized paths and unrelated
  test claims are rejected, and unsupported test generation ends safely.
- [ ] Remove hardcoded pytest file generation from `TestingAgent`; let the
  validated small plan own only `test_mutations`.
- [ ] Validate mutation paths against the profile before Repository MCP write,
  then run the native test command through Quality MCP.
- [ ] Raise Testing output budget to cover one bounded complete test file and
  verify its schema budget regression.
- [ ] Verify agent/runtime/workflow tests.

## Phase 7 — Delivery gates, documentation, and acceptance

### Task 10: Capability-aware approval and operator documentation

**Files:**
- Modify: `src/engineering_team/graph/stategraph.py`
- Modify: `src/engineering_team/contracts/models.py`
- Modify: `docs/architecture/overview.md`
- Modify: `docs/diagrams/architecture.md`
- Modify: `docs/diagrams/langgraph.md`
- Modify: `docs/evaluation.md`
- Modify: `README.md`
- Test: `tests/unit/test_delivery_gates.py`
- Test: `tests/integration/test_documentation.py`

- [ ] Add RED delivery-gate tests requiring successful evidence for every
  profile `required_capability` and reporting missing capability details.
- [ ] Implement gate/report fields without weakening current write/diff/test/
  security requirements.
- [ ] Document supported ecosystems, ambiguity, native commands, all-agent
  policies, local Langfuse degradation, and HF offline verification.
- [ ] Verify delivery and documentation tests.

### Task 11: Cross-ecosystem deterministic verification

**Files:**
- Create: `tests/integration/test_cross_ecosystem_workflow.py`
- Update: `specs/002-project-capability-agent-policies/tasks.md`

- [ ] Run Python and Node integration workflows plus one compiled profile
  command-routing fixture.
- [ ] Run focused MCP, graph, runtime, agent, observability, delivery, and
  documentation suites.
- [ ] Run the full pytest suite and Ruff.
- [ ] Run `git diff --check` and inspect staged/unstaged state, preserving all
  pre-existing report changes.

## Phase 8 — Generic causal remediation architecture

### Task 12: Preserve downstream causes and bounded model ownership

**Files:**
- Modify: `src/engineering_team/models/context.py`
- Modify: `src/engineering_team/graph/stategraph.py`
- Modify: `src/engineering_team/llm/runtime.py`
- Modify: `src/engineering_team/llm/policies.py`
- Modify: `src/engineering_team/agents/developer.py`
- Modify: `src/engineering_team/agents/testing.py`
- Test: `tests/unit/test_context.py`
- Test: `tests/unit/test_delivery_gates.py`
- Test: `tests/unit/test_model_runtime.py`
- Test: `tests/unit/test_policies.py`
- Test: `tests/unit/test_developer_agent.py`
- Test: `tests/integration/test_workflow.py`

**Interfaces:**
- `RemediationContext` carries one latest bounded causal validation result.
- `TestingMutationPlan` owns at most one unique test mutation.
- `DeveloperAgent.validate_update_preservation(...)` gates Python updates.
- `ArtifactPolicy.monotonic_fields` protects Security while allowing stronger findings.

- [x] Add RED tests for causal Testing/Security evidence visibility without
  execution permission and Reviewer consequence/cause separation.
- [x] Add RED tests for one-file Testing plans, duplicate rejection, behavioral
  setup, bounded repair, and explicit exhausted-quality termination.
- [x] Add RED tests rejecting destructive Python replacement before Repository
  MCP write and accepting preserved or explicitly authorized boundaries.
- [x] Add deterministic and mocked-model Security monotonicity tests plus
  bounded RAG content/provenance tests.
- [x] Add the real-StateGraph, mocked-HTTP, real Repository/Quality MCP causal
  integration regression from first test failure through second mutation and
  `APPROVED`.
- [x] Run focused deterministic suites. Keep the single real-model acceptance
  pending until every non-live verification gate is green.

### Task 13: Single live acceptance after deterministic readiness

**Generated evidence only:**
- `evaluation/reports/manual-password-fixed.json`
- matching isolated workspace and trace under `evaluation/reports/traces/`

- [ ] Run exactly one real Spanish password-change requirement with
  `HF_HUB_OFFLINE=1`; require `APPROVED`, Repository MCP writes, real diff,
  behavioral test success, six valid final role executions, and no unrecovered
  Langfuse `ERROR` event.
- [ ] If it fails, diagnose that completed run and add a new generic RED test;
  do not immediately rerun, weaken gates, or hardcode the requirement.

## Execution order

Tasks execute sequentially because contracts feed MCP, MCP feeds the graph,
the graph feeds agent policies/context, and Testing/delivery depend on all
previous layers. Task 12 hardens the resulting remediation loop before the
single live acceptance. Each task ends at a focused GREEN checkpoint. No phase
may be marked complete from code inspection alone.
