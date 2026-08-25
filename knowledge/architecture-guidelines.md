# Architecture Guidelines

## Boundaries and responsibilities

Define a clear responsibility for every component and keep dependencies directed through explicit interfaces. A component that owns a business rule should expose the smallest API needed by its callers. Separate orchestration, domain decisions, persistence, external integrations, and observability so failure handling remains visible. Preserve the six agent roles and keep routing decisions in deterministic graph code rather than prompts or model output.

## APIs and contracts

Describe request inputs, structured outputs, error cases, authorization boundaries, and compatibility expectations before proposing implementation. Prefer typed contracts that reject invalid states early. When an endpoint changes, identify the caller, service, repository, and response contract that are affected. Keep validation at the boundary and do not leak provider-specific details into domain contracts.

## Data and dependencies

Record whether a change reads, writes, migrates, or exposes data. Scope data access by the authenticated actor and make ordering and limits deterministic. New dependencies require a specific responsibility and must not duplicate an existing layer. External calls need timeouts, bounded retries, safe error mapping, and an observable fallback policy.

## Risk and validation

Assess coupling, authorization, data integrity, availability, and rollback risk. Proposals should name affected components and inspected files, then define focused tests for contracts, integration boundaries, and remediation routing. Preserve completed evidence after failure. A design is complete only when its assumptions, tradeoffs, validation strategy, and operational signals can be reviewed independently.
