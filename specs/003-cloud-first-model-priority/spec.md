# Feature Specification: Cloud-First Model Priority and Non-Actionable Remediation

**Feature ID:** 003-cloud-first-model-priority
**Status:** Implemented
**Governing document:** `.specify/memory/constitution.md` (Principle IX)

## 1. Purpose

Root-cause analysis of a real LIVE run (`evaluation/reports/manual-password-final-live.json`,
run `multimodel-7a3c26ed-2dfc-44d3-8f35-3873372e226d`) proved that:

1. causal remediation evidence propagation works correctly (Developer remediation
   receives the real downstream `run_tests`/security failure), but
2. the local `qwen3.5:9b` model, given real causal evidence twice, still returned
   zero applicable mutations both times, and the workflow burned the remaining
   `MAX_ITERATIONS` doing nothing observably different before ending `INCOMPLETE`.

This feature makes two changes, required together:

- **CLOUD_FIRST default execution.** A configured cloud provider becomes the
  primary inference path for all six agents; local Ollama models remain a
  bounded fallback and an explicit offline/local-only option. This does not by
  itself fix (2), but it changes which model is asked first and removes the
  false assumption that local-first is architecturally required.
- **Deterministic non-actionable-remediation termination.** Independently of
  which provider is primary, a Developer remediation cycle that produces zero
  applicable mutations and no structured blocker is classified immediately
  (not inferred from narrative text), a single bounded cross-provider fallback
  is attempted with the same causal evidence, and if that also fails to
  produce an applicable outcome the run terminates `HUMAN_REVIEW_REQUIRED`
  with a distinct reason instead of silently repeating the same no-op cycle.

## 2. Scope

In scope: model-provider selection strategy, cloud runtime prompt/context
parity with the local runtime, escalation-budget semantics, Developer
remediation actionability contract, merged Security+Testing causal evidence
for a generic pre-gate rejection. Out of scope: new agents, new orchestrators,
new tools, changes to `MAX_ITERATIONS=3`, changes to the six-agent
architecture, or any workflow-domain fallback trigger (`TOOL_ERROR`,
`MCP_ERROR`, `RAG_ERROR`, a failing test, a Security finding, a Reviewer
rejection) — those remain governed outcomes, never provider failures.

## 3. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-001 | `Settings.model_priority` (env `MODEL_PRIORITY`) SHALL default to `CLOUD_FIRST` and accept `CLOUD_FIRST`, `LOCAL_FIRST`, `CLOUD_ONLY`, `LOCAL_ONLY`. |
| FR-002 | A central `resolve_runtime_order` function, not any agent, SHALL decide the primary/fallback runtime pair for a run from the configured strategy and the runtimes actually wired in. |
| FR-003 | `CLOUD_ONLY` and `LOCAL_ONLY` SHALL never invoke the other provider under any circumstance. |
| FR-004 | When only one runtime object is constructed for a run, that runtime SHALL become the sole primary with no fallback, regardless of configured priority. |
| FR-005 | `CloudModelRuntime.invoke_artifact` SHALL build the same role-specific system/user prompt, bounded `ContextEnvelope`, governed artifact basis, and internal plan schema (`DeveloperMutationPlan`/`TestingMutationPlan`) as `LocalModelRuntime`, via one shared `build_prompts`/`role_schema`/`merge_role_artifact` implementation. It SHALL NOT ask the provider to merely echo the deterministic candidate. |
| FR-006 | A primary-mode cloud call SHALL NOT consume `CloudBudget`; only a fallback-mode call consumes it, bounded by `MAX_CLOUD_ESCALATIONS_PER_AGENT`/`MAX_CLOUD_ESCALATIONS_PER_RUN`. |
| FR-007 | Cross-provider fallback SHALL trigger only for `LLM_AVAILABILITY_ERROR`, `LLM_QUALITY_ERROR`, `SECURITY_CONFLICT`, `AGENT_TIMEOUT`, or `NON_ACTIONABLE_REMEDIATION`. `TOOL_ERROR`, `MCP_ERROR`, and `RAG_ERROR` SHALL NOT trigger it. |
| FR-008 | `ImplementationResult`/`DeveloperMutationPlan` SHALL carry an optional `blocker` field restricted to `INSUFFICIENT_CONTEXT`, `ARCHITECTURE_GAP`, `REQUIREMENT_AMBIGUITY`, `UNSAFE_CHANGE`. |
| FR-009 | During a Developer remediation cycle (`remediation_request` set), if the primary provider's output is neither `APPLIED` nor carries a `blocker`, the graph SHALL classify `NON_ACTIONABLE_REMEDIATION`, attempt exactly one fallback-provider call with the same envelope/candidate, and re-check actionability. |
| FR-010 | If the fallback attempt is also non-actionable, the graph SHALL terminate the run `HUMAN_REVIEW_REQUIRED` with error `DEVELOPER_REMEDIATION_EXHAUSTED`, without another Reviewer visit and without incrementing `EngineeringState.iteration`. |
| FR-011 | `causal_remediation_request` SHALL surface every currently active downstream cause (Security FAIL and/or Testing FAIL) when the remediation category is generic/`IMPLEMENTATION` (the deterministic pre-gate), and SHALL surface only the targeted cause when the category is `SECURITY` or `TESTING`. |
| FR-012 | Governed-fact monotonicity, MCP write authority, RAG provenance, and the existing structured-output repair/HITL policy remain unchanged and apply identically regardless of which provider is primary. |

## 4. Non-goals

- A new agent, orchestrator, or parallel execution path.
- Per-blocker-type distinct routing beyond "stop looping and go to HITL"
  (`INSUFFICIENT_CONTEXT`/`ARCHITECTURE_GAP`/`REQUIREMENT_AMBIGUITY`/
  `UNSAFE_CHANGE` are recorded and available for a future targeted route; this
  feature only requires they count as actionable and stop the no-op loop).
- Changing `MAX_ITERATIONS`, HITL-on-CRITICAL, or workspace isolation.
- Hard-coding any specific requirement, error string, or sample project.

## 5. Acceptance evidence

- `tests/unit/test_model_priority.py` — priority resolution, degrade-to-sole-primary,
  primary vs. fallback budget isolation, `NON_ACTIONABLE_REMEDIATION` cloud eligibility.
- `tests/unit/test_delivery_gates.py::test_generic_pregate_remediation_merges_every_currently_active_cause`
  — merged Security+Testing evidence for a generic rejection.
- `tests/integration/test_workflow.py::test_cloud_first_non_actionable_developer_falls_back_to_local_and_approves`
  — end-to-end CLOUD_FIRST run where cloud is primary for every role, only
  Developer's non-actionable remediation cycle reaches the local fallback, and
  the run still reaches `APPROVED`.
- `tests/integration/test_workflow.py::test_cloud_and_local_both_non_actionable_ends_human_review_without_stale_loop`
  — both providers non-actionable ends `HUMAN_REVIEW_REQUIRED` with exactly one
  remediation cycle, no stale Reviewer replay.
- Full existing regression suite (`pytest -m "not live"`), Ruff, `git diff --check`.

## 6. Addendum — primary/secondary cloud chain (resilience)

A real LIVE Gemini smoke observed `HTTP 500 api_error "gemini-3.7-flash is
currently experiencing high demand"` — a genuine, contract-correct provider
capacity failure, not a request defect. `CLOUD_FIRST` was extended from a
two-level (cloud, local) order to three levels per role:
`PRIMARY_CLOUD -> SECONDARY_CLOUD -> LOCAL`. `CloudModelRuntime.invoke_artifact`
now walks a per-role two-provider chain (`llm/cloud.py::_CLOUD_CHAIN`) inside
one call for provider errors (`LLM_AVAILABILITY_ERROR`/`AGENT_TIMEOUT`/
`LLM_QUALITY_ERROR`); an explicit `start_index=1` lets the Developer
non-actionable-remediation path in `stategraph.py` target the secondary cloud
provider specifically, since a *successful-but-unhelpful* response isn't a
provider error and wouldn't otherwise advance the chain. `CLOUD_ONLY` walks
both cloud providers and never invokes Ollama; `LOCAL_ONLY` is unaffected.
Only the first chain position is free (no escalation budget consumed);
`SECONDARY_CLOUD` and `LOCAL` are provider fallbacks and consume
`CloudBudget` like before. See `tests/unit/test_cloud_chain.py` and the
`ChainedCloudDeveloper`-based tests in `tests/integration/test_workflow.py`.
