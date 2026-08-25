# Architecture

`engineering_team.cli` is the composition root. It constructs adapters and a
single LangGraph `StateGraph`; no agent selects a node or model. Contracts and
configuration form the inner boundary, agents consume `ContextEnvelope`
projections, and adapters (`llm`, `rag`, `mcp`, `workspace`, `observability`)
depend inward without importing graph logic.

`EngineeringState` preserves validated stage artifacts, RAG evidence,
ToolResults, ModelExecutionInfo, errors, iteration, trace correlation and the
FinalReport. Nodes return patches and do not mutate the state in place.

Context isolation is explicit: Product sees only run/requirement; Architecture
receives product output and architecture/API evidence; Developer receives the
bounded design and repository context; Security sees only security/OWASP
evidence and scan results; Testing sees testing/coding evidence and quality
results; Reviewer receives validated summaries and provenance, never raw
repository contents or tool permissions.

Workspaces are copied to `workspace/runs/<run_id>` and Repository MCP resolves
every path beneath that copy. Cloud remains a sanitized, bounded contingency,
not an orchestrator or multi-model substitute.
