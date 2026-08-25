# Coding Standards

## Bounded changes

Implement the smallest change that satisfies the accepted specification and architecture. Inspect repository evidence before naming files or symbols. Keep modules focused, use existing abstractions, and avoid unrelated refactors. A proposed change must identify inspected paths, relevant symbols or component boundaries, concrete per-file behavior, API or data implications, security surface, and a validation strategy.

## Types and contracts

Use typed Python interfaces and validated structured outputs at trust boundaries. Prefer explicit enums and models over free-form status strings. Preserve governed facts such as tool results, evidence references, routing decisions, and error categories. Invalid structured output should enter bounded repair handling rather than being silently accepted or replaced with fabricated evidence.

## Safe repository operations

All file operations stay inside the configured workspace. Resolve and validate paths, reject traversal and symlinks, and deny secret files such as `.env` and `.env.*`. Write only through authorized roles and preserve a real diff from the original content. Tool summaries must be useful for review without copying credentials, environment values, or unnecessary file contents.

## Verification and failure handling

Add a failing focused test before a behavior change, implement the minimum correction, then run related integration and regression suites. Distinguish transport unavailability, functional tool failure, model availability, timeout, and invalid output. Use bounded retries and deterministic remediation. Log safe error categories and preserve evidence so a workflow failure ends with an explained result instead of collapsing.
