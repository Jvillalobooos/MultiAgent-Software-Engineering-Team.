# Testing Strategy

## Happy paths and business rules

Translate each acceptance criterion into an observable test. Verify password reset expiry at fifteen minutes and single-use behavior, account locking after five failed attempts, and transaction history restricted to the authorized user's latest five records. Assert structured outputs and final workflow status, not only that a function returned without exception.

## Errors and edge cases

Cover boundary values, empty data, malformed requests, repeated operations, timeout, unavailable dependencies, and partial progress. Distinguish an MCP transport failure from a tool that ran and reported a functional failure. Confirm invalid model output follows bounded repair policy, connection failures remain availability errors, and real timeouts become `AGENT_TIMEOUT` with preserved evidence.

## Security and isolation

Test authentication and authorization separately. Include cross-user identifiers, IDOR attempts, non-expiring or reused tokens, path traversal, symlinks, and secret files. Use only synthetic sentinels when testing secret boundaries. Confirm role allowlists and workspace isolation through the real MCP protocol, and verify that unsafe input never appears in evidence or exported traces.

## Integration and regression

Exercise the LangGraph sequence, conditional remediation, third-rejection HITL, RAG provenance, persistent Chroma retrieval, stateful MCP getters, and real repository diffs. A failed quality tool must influence reviewer routing. Run focused tests first, then graph, integration, E2E, lint, and the full suite. Live evaluation metrics must come from actual local model calls and must retain expected outcomes rather than changing them to match observations.
