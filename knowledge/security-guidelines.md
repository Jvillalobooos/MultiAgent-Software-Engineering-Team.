# Security Guidelines

## Authentication and session controls

Verify identity at trusted boundaries and keep authentication state separate from authorization decisions. Password recovery must avoid account enumeration, use high-entropy reset tokens, enforce single use, and expire tokens after the specified fifteen-minute window. Account locking should activate after five failed attempts while preserving safe recovery and audit evidence. Do not place credentials or tokens in prompts, traces, diffs, or tool summaries.

## Authorization and object access

Every object access must be scoped to the authenticated actor or an explicit permitted role. A supplied user or transaction identifier is not authorization. Enforce ownership in the service or data query before returning data, and deny cross-user requests consistently. Collection endpoints should apply authorization before limits so filtering cannot expose arbitrary records or conceal an insecure query.

## Validation, secrets, and logging

Validate untrusted input by type, format, length, and allowed values. Use parameterized storage operations and bounded output schemas. Secret paths such as `.env` and `.env.*` are deny-by-default for listing, reading, and search; symlinks and paths outside the workspace are also rejected. Logs and Langfuse observations should contain categories, identifiers, timing, and sanitized summaries, never credential values.

## Abuse, dependencies, and review

Rate-limit sensitive endpoints and detect repeated failures without exposing account state. Pin and scan dependencies using the approved quality tools. Security review should cite retrieved guidance and MCP evidence, classify findings by severity, and force human review for critical issues. Functional scanner failures trigger remediation; unavailable MCP transport is recorded separately as `MCP_ERROR` and cannot result in automatic approval.
