# Architecture

`engineering_team.cli` is the composition root. It constructs adapters and a
single LangGraph `StateGraph`; no agent selects a node or model. Contracts and
configuration form the inner boundary, agents consume `ContextEnvelope`
projections, and adapters (`llm`, `rag`, `mcp`, `workspace`, `observability`)
depend inward without importing graph logic.

`EngineeringState` preserves validated stage artifacts, RAG evidence,
ToolResults, ModelExecutionInfo, errors, iteration, trace correlation and the
FinalReport. Nodes return patches and do not mutate the state in place.

Before Product, the deterministic `ProjectCapabilities` node asks Repository
MCP to derive a strict profile for Python, Node/TypeScript, .NET, Java, Go, or
Rust. Unknown, ambiguous, or mandatory-capability-missing projects record
`PROJECT_CAPABILITY_ERROR` and finish `INCOMPLETE` before any model or
subprocess can mutate state. Repository and Quality derive the profile
independently; only the profile fingerprint crosses the Quality boundary, and
commands always execute as argv with `shell=False`.

Context isolation is explicit. All six agents receive the sanitized validated
profile plus only their role projection. A central field-policy registry
classifies every artifact field as exact, additive, enrichable, mutable, or
monotonic, and the same policy drives prompts and semantic validation. Developer receives at
most two complete bounded inspected source files, prioritizing its candidate
paths across remediation. Testing receives at most one guarded native test
example and may write only paths matched by that ecosystem's test patterns.

Remediation evidence is independent from tool execution authority. When a
downstream test or security validation fails, Developer can see the prior
implementation/diff, Reviewer reason, and one latest bounded causal
`ToolResult` with status, exception/assertion summary, and evidence reference.
Its allowlist does not gain `run_tests` or scanner permissions. Reviewer may
keep a generic delivery-gate reason for audit while its remediation request
contains the concrete structured cause.

Testing model ownership is limited to one unique `TestingMutationPlan` file.
Graph code owns execution, actual results, evidence, failures, and final test
status. Python replacements pass an AST preservation guard before Repository
MCP write so unrelated top-level functions, classes, and decorated routes
cannot disappear without explicit validated removal intent.

Security is monotonic: grounded model/RAG evidence may strengthen deterministic
`PASS` to `FAIL`, but never weaken an existing failure. Architecture, Security,
and Testing receive bounded relevant RAG fragment text together with source,
section, chunk, and score. Exhausted structured-output repair preserves
`LLM_QUALITY_ERROR` and routes to governed fallback/HITL; offline exhaustion is
explicit `HUMAN_REVIEW_REQUIRED`, not an ambiguous fallthrough.

Workspaces are copied to `workspace/runs/<run_id>` and Repository MCP resolves
every path beneath that copy. Cloud remains a sanitized, bounded contingency,
not an orchestrator or multi-model substitute.

La propuesta de evolución para ejecutar por defecto sobre `sample_app`,
persistir decisiones de Product y Architecture, y emitir resultados autónomos
está documentada en [Ejecuciones autónomas sobre Sample App](sample-app-autonomous-outcomes.md).

RAG ingestion uses LangChain Document and RecursiveCharacterTextSplitter as a
small integration layer before Sentence Transformers and persistent Chroma.
Tool execution crosses the official MCP stdio protocol through
`MCPRepositoryClient`/`MCPQualityClient` into independently exposed Repository
and Quality MCP Server surfaces; bounded backends retain sandbox and allowlists.
Quality re-detects the project for every build, lint, dependency, security, or
test operation and rejects a stale profile fingerprint without starting a
subprocess. Reviewer approval requires successful evidence for every capability
listed as mandatory by the validated profile.
