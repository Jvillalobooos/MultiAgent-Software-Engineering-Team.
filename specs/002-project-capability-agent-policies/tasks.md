# Tasks: Project Capability and Agent Policies

**Input:** `spec.md` and `plan.md` in this directory.

## Phase 1 — Recovery baseline

- [x] T001 Add and verify structured-output, bounded-context, Langfuse severity,
  and Langfuse connectivity regression coverage.

## Phase 2 — Capability foundation

- [x] T002 Define strict capability enums/models/state and fingerprint validation.
- [x] T003 Implement Python, Node/TypeScript, .NET, Java, Go, Rust, ambiguous,
  and unknown deterministic detection.

## Phase 3 — MCP boundary

- [x] T004 Expose capability evidence and guarded native test reads through
  Repository MCP direct and stdio clients.
- [x] T005 Execute only locally re-derived profile commands through Quality MCP
  with fingerprint verification.

## Phase 4 — Workflow integration

- [x] T006 Add the ProjectCapabilities node, typed errors, context projection,
  trace evidence, and safe pre-model `INCOMPLETE` route.

## Phase 5 — Six-agent behavior

- [x] T007 Centralize exact/additive/enrichable/mutation field policies and use
  them in prompts plus semantic validation for all six agents.
- [x] T008 Make Developer intent evidence-based and preserve relevant inspected
  context across remediation.

## Phase 6 — Native Testing

- [x] T009 Generate, guard, and execute only ecosystem-native tests from a
  bounded Testing mutation plan.

## Phase 7 — Delivery and acceptance

- [x] T010 Enforce profile-required validation evidence and update architecture,
  diagrams, evaluation, and README documentation.
- [x] T011 Verify cross-ecosystem fixtures and complete every deterministic
  regression, lint, and diff gate.
- [x] T012 Preserve bounded causal validation evidence across remediation,
  reduce Testing output ownership, guard destructive updates, enforce
  monotonic Security, expose bounded RAG content, and route exhausted model
  quality failures explicitly.
- [ ] T013 Run one real Spanish password-change acceptance only after T011 is
  complete; do not rerun immediately if it fails.

## Dependency order

`T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008 -> T009 -> T010 -> T012 -> T011 -> T013`

## Completion rule

A task is complete only after its named RED test was observed failing for the
expected reason and all focused tests pass after the minimal implementation.
The feature is complete only when the full suite, Ruff, diff checks, and real
functional acceptance all pass.
