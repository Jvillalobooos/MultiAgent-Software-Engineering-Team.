# Chat-First Multiagent Interface Design

**Date:** 2026-08-27

**Status:** Approved

## Purpose

Replace the form-led launch experience with a local, chat-first interface that remains coherent with the real multiagent backend. A user selects any local project folder, describes one task in natural language, watches one independent multiagent run, reviews its evidence and diff, and explicitly applies approved changes to the original project.

Each chat message starts a new run. Runs do not inherit conversational or task context from earlier messages, although the interface keeps their cards visible as session history.

## Current Problems

The current frontend defaults to `sample_app` and accepts a free-form project path. It can therefore run against a different project than the user intended. The selected run is copied to `workspace/runs/<run-id>`, and dry-run mode produces a proposed diff without writing either the isolated copy or the original project. The UI does not make this separation sufficiently prominent.

The WebSocket owns the only live delivery path and the backend discards a completed run after the terminal message is delivered. A completed report cannot be fetched again, a disconnected browser cannot recover state reliably, and there is no operation that applies a reviewed isolated result to the source project.

The mission view uses a viewport-locked layout, and parts of the debrief use fixed heights. These choices can clip content on smaller displays. Provider failures are reduced to an exception class, so an HTTP authentication failure, unavailable model, quota limit, and transient outage look the same in both the UI and Langfuse.

## User Experience

### Project selection

The application is local-only. A compact header displays the active project and provides a **Select folder** action. The action calls the backend, which opens the native Windows folder picker and returns either:

- the canonical absolute directory path and basic project metadata; or
- a cancellation result that leaves the existing selection unchanged.

The backend validates that the selected value is an existing directory. The path is displayed clearly and is included in every run record. Manual path entry is not the primary interaction.

### Chat shell

The primary screen resembles a chat rather than a technical configuration form. It contains:

- a compact project header;
- a scrollable history of task messages and run cards;
- a fixed composer for a natural-language task; and
- an **Execute** action.

The composer is disabled until a valid project is selected and while its message is being submitted. Submitting a message clears the composer and creates one independent run. It does not append prior messages to the agent requirement.

### Progressive run card

Each task message is paired with a run card that progressively reveals backend state:

1. **Preparing:** validates the project and creates an isolated workspace.
2. **Running:** shows the active agent, route graph, iteration, elapsed time, model/provider, fallback warnings, and ordered activity.
3. **Review:** shows final status, executed tests and tools, scorecard, model usage, errors, and changed files.
4. **Diff:** provides file tabs and a readable proposed/applied diff.
5. **Apply:** confirms the exact target and affected files, applies the approved result, and reports verification.

On wide screens, the active card may arrange the agent graph and activity in two columns. On narrow screens, all regions stack vertically. The page remains scrollable; no primary screen uses a fixed viewport height or hides overflow. Secondary evidence can be collapsed without hiding status, failures, or apply controls.

## Backend Architecture

### Project picker

A local project-selection endpoint invokes the Windows native directory dialog outside the browser process. It serializes picker requests so two dialogs cannot overlap and returns a typed result for selection, cancellation, or platform/display failure.

The picker endpoint is intended only for loopback use. The server must reject non-loopback access to the native-picker operation. Existing run endpoints continue to validate paths independently; a client cannot bypass validation by posting an arbitrary invalid path.

### Run lifecycle

`POST /api/runs` accepts the selected canonical project path and one natural-language requirement. The backend generates the test intent from that requirement unless a future advanced control supplies it; the chat flow does not expose the current test-specification form.

Every run records:

- run identifier;
- original canonical project path;
- isolated workspace path;
- task message;
- source-project fingerprint captured before work begins;
- normalized status;
- ordered events;
- final report and diff, when available; and
- apply attempt and verification result, when available.

The normalized status set is:

`queued`, `preparing`, `running`, `review_required`, `approved`, `failed`, `applying`, `applied`, and `apply_failed`.

Run records survive WebSocket disconnects and terminal delivery. The backend exposes read endpoints for run summaries, a complete run snapshot, and ordered events after a cursor. Persistence is file-backed beneath the configured workspace root so a local server restart can reconstruct completed and interrupted runs.

The WebSocket remains the low-latency transport. On connection or reconnection, the frontend first loads a run snapshot, then subscribes using the last observed event sequence. Events have stable identifiers and monotonically increasing sequence numbers so replay cannot duplicate activity.

### Isolation and output

All agent and quality-tool activity operates on `workspace/runs/<run-id>`, never directly on the source project. Dry-run-only semantics are removed from the primary chat: producing changes always means producing them inside the isolated workspace. The final report distinguishes:

- files actually changed inside the isolated workspace;
- files only proposed by a model but not written;
- test commands actually executed and their results; and
- whether any change has been applied to the source project.

An approved score alone never implies that files were written.

### Applying changes

Only a completed run with an approved review and an actual isolated-workspace diff can be applied. The apply request includes the run identifier and an explicit confirmation of the original canonical path.

Before writing, the backend:

1. recomputes the source-project fingerprint for affected paths;
2. blocks with a conflict result if those paths changed since the run started;
3. validates every relative path remains inside both project roots;
4. creates a run-scoped backup of affected source files and records files that did not previously exist; and
5. stages replacement content in temporary files before performing atomic file replacements where supported.

After writing, the backend executes the run's verified test command against the original project. The apply result contains written paths, test output, exit status, duration, and backup location. If writing fails partway, the backend restores the backup automatically. If writing succeeds but verification fails, it reports `apply_failed` and offers an explicit restore operation; it does not silently erase the written result.

A restore operation is allowed only for that run's backup and performs the same path and conflict checks. The interface clearly states whether restoration is automatic, available, completed, or blocked.

## Frontend–Backend Contract

Python response models and TypeScript validators share the same fields and status meanings. The frontend renders only data received from the backend; it does not calculate approval, invent changed files, infer test success, or convert provider warnings into fatal run failures.

Provider fallbacks are warnings when a later attempt succeeds. A run becomes `failed` only when the orchestrator cannot produce a terminal reviewable result. `review_required` represents a deliberate human gate, not a transport error.

Required API capabilities are:

- open the local folder picker;
- create one run from one message;
- list run summaries for the current local installation;
- fetch a complete run snapshot;
- retrieve events after a sequence cursor;
- subscribe to live events;
- apply an approved run; and
- restore an eligible run backup.

All error responses use a stable code, a user-safe message, a recoverability flag, and optional structured details. Secrets, authorization headers, prompts containing sensitive fragments, and raw provider bodies are never returned to the browser.

## Observability

Run, trace, and event identifiers are correlated. Langfuse records the original project label, isolated workspace label, run status transitions, apply status, and sanitized provider failures.

For HTTP provider failures, observability captures provider, requested model, HTTP status, retryability, latency, and a bounded sanitized error category. It does not store API keys or an unrestricted response body. This makes invalid credentials, quota exhaustion, missing models, rate limits, and transient service failures distinguishable.

The UI links warnings to the affected agent attempt and shows whether a fallback later succeeded.

## Error Handling

- Cancelling the folder dialog preserves the current project and does not display an error.
- Picker unavailability provides a recoverable manual-path fallback for the local session.
- Invalid or missing directories prevent run creation.
- A failed workspace copy produces a terminal `failed` run with no agent execution.
- A lost WebSocket triggers snapshot reload and cursor-based reconnection with bounded backoff.
- A browser reload reconstructs existing run cards from persisted backend snapshots.
- Provider failure uses the warning/fatal distinction defined above.
- Source changes after run creation produce an apply conflict and never overwrite the source.
- Apply and restore operations are idempotent: repeating a completed request returns its recorded outcome rather than writing twice.

## Security Boundaries

The native picker is loopback-only. Every path received or recovered by the backend is canonicalized before use. Project-relative paths may not be absolute, contain traversal outside the selected root, or resolve through links to an unauthorized destination.

The system never applies model-supplied paths directly. The deterministic repository layer governs the affected path set, and the apply layer revalidates it. Backups live under the run workspace, not inside the selected project, and are never exposed as arbitrary download paths.

## Testing Strategy

### Backend tests

Tests cover picker selection, cancellation and overlapping requests; project validation; one run per message; persistent snapshots; event ordering and replay; reconnect behavior; isolation; status transitions; source fingerprint conflicts; safe apply; partial-write rollback; post-apply verification; explicit restore; path traversal and link rejection; idempotency; and provider error sanitization.

Native dialog behavior is abstracted behind a small picker interface. Automated tests use a deterministic fake while a Windows smoke test exercises the actual adapter.

### Contract tests

Fixtures produced from backend models are validated by frontend runtime guards. Tests cover every status, warning, final report, apply result and error shape. A schema mismatch must fail visibly rather than rendering fabricated defaults.

### Frontend tests

Tests cover project selection, cancellation, composer validation, one independent run per message, progressive card transitions, fallback warnings, reconnect and snapshot recovery, responsive stacking, diff navigation, apply confirmation, conflict handling, verification failure and restoration state.

### End-to-end test

An end-to-end scenario copies `demo-projects/calculadora-qa-demo` to a temporary project, selects that directory through the picker abstraction, submits one small task, observes real backend events, reviews an actual isolated diff, applies it, verifies the source file changed, and confirms the project's tests ran. The committed demo project is never modified by automated validation.

## Acceptance Criteria

- A user can select any existing local directory through the native Windows folder dialog.
- The selected canonical path remains visible throughout each run.
- Every submitted chat message starts exactly one independent backend run.
- The displayed graph, status, events, files, tests and approval match persisted backend data.
- A disconnect or reload does not lose completed or active run information.
- Agents and tools operate only on an isolated project copy.
- The UI never labels a proposed-only diff as written.
- An approved isolated diff can be explicitly applied to an unchanged original project.
- Conflicting source edits are detected before any overwrite.
- Apply results identify exact writes and real post-apply test results.
- The interface remains usable without clipped primary content on desktop and narrow screens.
- Langfuse distinguishes sanitized provider HTTP failure categories while preserving secret redaction.
- The calculator end-to-end scenario passes against a temporary copy.

## Out of Scope

- Remote or multiuser deployment.
- Shared conversations or inherited context between task messages.
- Direct agent writes to the original project during execution.
- Git commits, pushes or pull requests created automatically.
- Selecting individual files instead of a project directory.
- Operating-system folder pickers other than Windows in this iteration.
