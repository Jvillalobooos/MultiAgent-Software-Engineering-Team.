# SDD governance

Before relevant changes, read the applicable SDD artifacts. Precedence is
Constitution > Spec > Plan > Tasks > implementation. Constitution defines
invariants, Spec defines what, Plan defines how, and Tasks define executable
work. Changes to requirements, acceptance criteria, Pydantic contracts, agent
responsibilities, architecture, EngineeringState, LangGraph routing, RAG, MCP,
multi-model, fallback, guardrails, or HITL require updating the governing SDD
artifact first. Approved behavior is implemented from a Task with evidence.

## Project invariants

There are exactly six runtime agents: Product, Architecture, Developer,
Security, Testing, and Reviewer. LangGraph StateGraph is the only
orchestrator. LLMs recommend; deterministic code governs routing, limits, and
gates. `MAX_ITERATIONS=3`; Security `CRITICAL` routes to HITL.

## Multi-model and cloud

The only MVP+ bonus is deterministic local multi-model execution via Ollama:
Product/Developer/Security/Reviewer use `qwen3.5:9b`; Architecture/Testing use
`qwen3.5:4b`. Agents never choose models. Cloud is contingency, not bonus:
Product/Architecture/Reviewer use Gemini 3.7 Flash; Developer/Security use
Groq `openai/gpt-oss-120b`; Testing uses Groq `openai/gpt-oss-20b`. Never send
secrets or `.env` to cloud. MCP, RAG, and tool failures do not auto-escalate.

## Engineering rules

Use Python 3.10+, Pydantic for decision-affecting outputs, minimum agent
context, RAG provenance, MCP least privilege, workspace sandboxing, pytest for
behavior changes, and proportional evidence for documentation/configuration.
Never expose secrets in code, prompts, logs, or traces; never invent evidence
or change evaluation outcomes to pass tests.

Do not introduce Parallel Agents, Memory, Auto-PR, Qdrant, n8n, microservices,
or a complex UI without an explicitly approved SDD change.
