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
every path beneath that copy. By default (`local_first=true`) cloud is a
sanitized, bounded contingency: Ollama runs every agent and Gemini/Groq only
step in, budget-capped, after a local failure. Setting `CLOUD_ENABLED=true`
and `LOCAL_FIRST=false` reverses the priority — `CloudModelRuntime` becomes
the primary runtime for all six agents (still schema-constrained and
governed-facts-checked, still routed per role through the fixed
Gemini/Groq map) and `LocalModelRuntime`/Ollama becomes the safety-net
fallback if a cloud call fails. Either way, cloud never becomes the
orchestrator: LangGraph routing, guardrails, and governed facts are identical
regardless of which runtime executes a node. Both runtimes build their
prompts from the same role-specific `prompts/<role>/system.md` files via
`engineering_team.llm.prompting`, so provider choice never changes what an
agent is allowed to do.

RAG ingestion uses LangChain Document and RecursiveCharacterTextSplitter as a
small integration layer before Sentence Transformers and persistent Chroma.
Tool execution crosses the official MCP stdio protocol through
`MCPRepositoryClient`/`MCPQualityClient` into independently exposed Repository
and Quality MCP Server surfaces; bounded backends retain sandbox and allowlists.
