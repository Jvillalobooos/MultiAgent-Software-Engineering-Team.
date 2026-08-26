# Tasks: Cloud-First Model Priority and Non-Actionable Remediation

**Input:** `spec.md` and `plan.md` in this directory.

## Phase 1 — Contracts and configuration

- [x] T001 Add `ModelPriority`, `DeveloperBlocker`, `NON_ACTIONABLE_REMEDIATION`,
  and `DEVELOPER_REMEDIATION_EXHAUSTED` to `contracts/enums.py`; add
  `ImplementationResult.blocker`; add `Settings.model_priority`
  (default `CLOUD_FIRST`, env `MODEL_PRIORITY`) and flip `cloud_enabled`
  default to `True`; remove the dead `local_first` field.

## Phase 2 — Shared provider pipeline

- [x] T002 Extract `build_prompts`/`role_schema`/`merge_role_artifact` as
  module-level functions in `llm/runtime.py` shared by both runtimes; add the
  `blocker` field to `DeveloperMutationPlan` and to the Developer
  `ArtifactPolicy.mutation_fields`.
- [x] T003 Rewrite `CloudModelRuntime.invoke_artifact` to build real
  role-specific prompts/schemas via the shared pipeline (never an echo),
  support `mode="primary"|"fallback"`, and skip `CloudBudget` consumption for
  primary calls.
- [x] T004 Add `llm/priority.resolve_runtime_order` and wire
  `build_engineering_graph(..., model_priority=...)` to use it at the single
  per-role invocation call site, replacing the hardcoded local-primary order.

## Phase 3 — Non-actionable remediation

- [x] T005 Classify `NON_ACTIONABLE_REMEDIATION` deterministically from the
  structured `ImplementationResult` (`action_mode`/`blocker`), attempt exactly
  one bounded cross-provider fallback with the same causal evidence, and
  terminate `HUMAN_REVIEW_REQUIRED`/`DEVELOPER_REMEDIATION_EXHAUSTED` without
  another Reviewer visit or iteration increment when both attempts fail.
- [x] T006 Merge active Security+Testing causal evidence for a generic/
  `IMPLEMENTATION` pre-gate rejection in `causal_remediation_request`, keeping
  a targeted `SECURITY`/`TESTING` category single-cause.

## Phase 4 — Regression and new coverage

- [x] T007 Fix every existing test broken by the new default (`model_priority`
  degrade-to-sole-primary, `mode` kwarg on test-double `invoke_artifact`
  stubs, the `blocker` property in Developer-schema mock matchers, explicit
  `model_priority="local_first"` on tests that specifically exercise the old
  local-fails/cloud-fallback mechanism).
- [x] T008 Add `tests/unit/test_model_priority.py` (priority resolution,
  graceful degrade, budget isolation, cloud eligibility) and a merged-evidence
  regression in `tests/unit/test_delivery_gates.py`.
- [x] T009 Add end-to-end integration coverage: CLOUD_FIRST primary with a
  non-actionable Developer remediation cycle falling back to local and still
  reaching `APPROVED`; both providers non-actionable ending
  `HUMAN_REVIEW_REQUIRED` with exactly one remediation cycle and no stale
  Reviewer replay.

## Phase 5 — Documentation and verification

- [x] T010 Update the constitution (Principle IX) and this spec/plan/tasks
  triad before/alongside the implementation.
- [x] T011 Full non-live suite, Ruff, `git diff --check` all pass.
- [ ] T012 One real Spanish password-change LIVE acceptance under the new
  CLOUD_FIRST default, only after the user explicitly requests it.

## Dependency order

`T001 -> T002 -> T003 -> T004 -> T005 -> T006 -> T007 -> T008 -> T009 -> T010 -> T011 -> T012`

## Completion rule

A task is complete only after the full non-live suite, Ruff, and
`git diff --check` pass together. T012 requires explicit user approval before
any LIVE/Ollama/cloud-credentialed run — never run automatically after a
code change.
