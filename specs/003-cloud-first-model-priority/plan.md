# Plan: Cloud-First Model Priority and Non-Actionable Remediation

**Input:** `spec.md` in this directory; Principle IX of the constitution.

## Architecture

### Provider selection

- `engineering_team.contracts.enums.ModelPriority` — `CLOUD_FIRST` (default),
  `LOCAL_FIRST`, `CLOUD_ONLY`, `LOCAL_ONLY`.
- `Settings.model_priority` reads `MODEL_PRIORITY` from the environment.
  `Settings.cloud_enabled` defaults to `True` (per-role activation still
  requires a configured API key via `CloudRouter.enabled_for`).
- `engineering_team.llm.priority.resolve_runtime_order(priority, local, cloud)`
  is the single deterministic authority for primary/fallback selection. It
  degrades gracefully to the sole runtime actually constructed when the other
  was never wired in, and never builds a fallback for `CLOUD_ONLY`/`LOCAL_ONLY`.
- `build_engineering_graph(..., model_priority=...)` computes `runtime_order`
  once and uses it at the single per-role model-invocation call site instead
  of the previous hardcoded local-primary/cloud-fallback order.

### Shared prompt/schema/merge pipeline

- `engineering_team.llm.runtime` exposes `build_prompts` (module-level,
  extracted from the former `LocalModelRuntime._prompts` method),
  `role_schema` (per-role internal plan schema + artifact basis), and
  `merge_role_artifact` (merges a validated internal plan back into the full
  governed artifact). Both `LocalModelRuntime.invoke_artifact` and
  `CloudModelRuntime.invoke_artifact` call these same three functions, so a
  cloud-primary Developer/Testing call goes through the identical
  `DeveloperMutationPlan`/`TestingMutationPlan` contract and governed-fact
  check (`preserves_governed_facts`) as a local call — never a bare echo.
- `CloudModelRuntime.invoke_artifact(..., mode="primary"|"fallback",
  fallback_reason=...)`: `mode="primary"` skips `CloudBudget.consume`
  entirely; `mode="fallback"` consumes it exactly as before. `LocalModelRuntime`
  accepts the same keyword pair (ignored functionally, but stamped onto the
  returned `ModelExecutionInfo.fallback_used`/`fallback_reason` so trace/model
  usage evidence is accurate regardless of which provider acted as fallback).

### Non-actionable remediation

- `ImplementationResult` and `DeveloperMutationPlan` gain an optional
  `blocker: DeveloperBlocker | None` field (`INSUFFICIENT_CONTEXT`,
  `ARCHITECTURE_GAP`, `REQUIREMENT_AMBIGUITY`, `UNSAFE_CHANGE`), registered as
  a `mutation_field` in the Developer `ArtifactPolicy` alongside `mutations`.
- In `stategraph.make_node`, immediately after `apply_mutations` for
  `AgentRole.DEVELOPER`: if `current.remediation_request` is set (this is a
  remediation cycle) and the primary output is neither `APPLIED` nor carries a
  `blocker`, the graph records `ErrorCode.NON_ACTIONABLE_REMEDIATION`, calls
  `runtime_order.fallback.invoke_artifact(..., mode="fallback",
  fallback_reason=...)` once with the same envelope/candidate, and re-applies
  mutations. If the result is still not actionable, it appends
  `ErrorCode.DEVELOPER_REMEDIATION_EXHAUSTED` and returns
  `human_review_required=True` directly from the node — bypassing Reviewer
  entirely for this cycle and without incrementing `iteration` (iteration only
  advances on an actual Reviewer rejection).
- `governed_terminal_route` treats both new error codes as HITL-eligible
  (`HUMAN_REVIEW_REQUIRED`), matching the existing `LLM_QUALITY_ERROR` policy
  rather than falling through to an unexplained `INCOMPLETE`.

### Merged causal evidence

- `causal_remediation_request` is restructured around a `_causal_segment`
  helper. A targeted `RemediationCategory.SECURITY`/`TESTING` rejection
  surfaces only its own cause (unchanged prior behavior). A generic/
  `IMPLEMENTATION` pre-gate rejection — the deterministic gate's actual
  category — now surfaces every currently active cause (Security FAIL and/or
  Testing FAIL) instead of only the first one found, so Developer sees the
  complete picture in one remediation cycle.

## Compatibility and rollout

- `Settings.cloud_enabled` flips its default to `True`; without a configured
  API key, `CloudRouter.enabled_for` still returns `False` per role, so a
  deployment with no cloud credentials degrades to local-only behavior
  automatically — no code change required, matching "cloud credentials are
  optional."
- `Settings.local_first: bool` is removed (it was already dead — nothing
  read it) in favor of `Settings.model_priority`.
- `run_multimodel_acceptance`/CLI pass `model_priority=settings.model_priority`
  through unchanged otherwise.
- Existing tests that specifically exercise "local fails, cloud fallback
  succeeds" pass `model_priority="local_first"` explicitly, preserving their
  tested mechanism under the new default; every test double's `invoke_artifact`
  stub accepts the new `mode`/`fallback_reason` keywords.

## Testing

TDD: existing suite adjusted for the new `blocker` schema field and default
priority (fixed first, confirming exactly which assertions encoded the old
LOCAL_FIRST-only assumption), then new coverage added per `spec.md` §5.
