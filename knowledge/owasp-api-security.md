# OWASP API Security Practices

## Object-level authorization

Prevent IDOR and broken object-level authorization by checking permission for every requested object. Do not accept an arbitrary `user_id`, account identifier, or transaction identifier as proof of access. Prefer owner-scoped repository queries derived from the authenticated principal. Return a safe denial for cross-user access and test both direct object lookup and collection filtering.

## Authentication and sensitive flows

Protect login, account locking, and password recovery from brute force and enumeration. Recovery tokens require unpredictable values, a narrow purpose, single-use consumption, and an explicit expiration. A non-expiring reset token is a security failure. Apply consistent responses and safe audit events while ensuring rate limits and lock thresholds follow the specified business rules.

## Injection and data exposure

Validate request data and use parameterized queries or equivalent safe APIs. Limit response fields to the contract and do not expose credentials, internal stack traces, or unrelated user records. Enforce maximum collection sizes in the authorized data query. Treat logs, traces, tool results, and model context as potential disclosure surfaces and sanitize them before export.

## Resource use and verification

Bound request size, execution time, retries, and external calls. Dependency or scanner failures must be visible and classified. Security tests should cover unauthorized identifiers, malformed input, repeated attempts, expired and reused tokens, excessive results, and failure paths. Preserve source, section, chunk identifier, and score for retrieved evidence so the reviewer can distinguish grounded findings from unsupported claims.
