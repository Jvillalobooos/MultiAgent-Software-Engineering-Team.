# Autonomous Engineering Team Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first, hierarchical six-agent software-engineering
team governed by LangGraph, with deterministic routing, evidence-backed RAG
and MCP operations, and observable approval decisions.

**Architecture:** A modular Python monolith uses LangGraph `StateGraph` as the
only orchestrator around an immutable-by-convention `EngineeringState`.
Specialized agents receive `ContextEnvelope` projections instead of the full
state; adapters isolate Ollama, optional cloud providers, RAG, MCP, Langfuse,
and the workspace. Pydantic contracts and deterministic routers control every
state-changing result and transition.

**Tech Stack:** Python 3.10+, LangGraph, LangChain where integration value is
demonstrable, Pydantic, Ollama, Sentence Transformers, Chroma, Langfuse,
pytest, FastAPI, SQLite, Repository MCP, Quality MCP, CLI.

**Spec:** `specs/001-autonomous-engineering-team/spec.md`

## Global constraints

- LangGraph `StateGraph` is the only workflow orchestrator; no agent or LLM
  chooses a graph transition directly.
- Exactly six core roles exist: Product, Architecture, Developer, Security,
  Testing, and Reviewer.
- Use a modular monolith. Do not introduce parallel agents, memory, Auto-PR,
  Qdrant, n8n, microservices, a complex UI, models, or cloud providers beyond
  the governed set.
- Use Pydantic for every decision-affecting input, output, error, tool result,
  model execution record, and final report.
- Enforce `MAX_ITERATIONS=3`, `MAX_LOCAL_RETRIES=1`,
  `MAX_LOCAL_REPAIRS=1`, `MAX_CLOUD_ESCALATIONS_PER_AGENT=1`, and
  `MAX_CLOUD_ESCALATIONS_PER_RUN=3` in deterministic code.
- The multi-model local run is the sole MVP+ bonus. Cloud fallback is
  resilience only and never contributes evidence for that bonus.
- All workspace operations stay inside a per-run isolated copy. Paths with
  traversal, resolved external destinations, or secrets are rejected.
- Documentation-only work uses proportional document validation; behavior
  changes require executable proportional tests and objective evidence.

---

## 1. Locked repository structure and dependency direction

The implementation shall create the following structure. File names listed
here are the authoritative implementation destinations for later Tasks; this
plan does not create them now.

```text
src/engineering_team/
  __init__.py
  cli.py
  config.py
  contracts/
    enums.py
    models.py
    state.py
  agents/
    base.py
    product.py
    architecture.py
    developer.py
    security.py
    testing.py
    reviewer.py
  prompts/
    product/{system.md,user.md}
    architecture/{system.md,user.md}
    developer/{system.md,user.md}
    security/{system.md,user.md}
    testing/{system.md,user.md}
    reviewer/{system.md,user.md}
  models/
    context.py
    policy.py
  graph/
    stategraph.py
    nodes.py
    routers.py
    hitl.py
  llm/
    registry.py
    router.py
    ollama.py
    cloud.py
    repair.py
  rag/
    loaders.py
    chunking.py
    index.py
    retrievers.py
    provenance.py
  mcp/
    contracts.py
    repository.py
    quality.py
    permissions.py
  observability/
    langfuse.py
    metrics.py
    evaluation.py
  guardrails/
    validation.py
    routes.py
    secrets.py
    timeouts.py
  workspace/
    isolation.py
    paths.py
    runs.py
knowledge/
  architecture-guidelines.md
  api-design-guidelines.md
  coding-standards.md
  security-guidelines.md
  owasp-api-security-guidelines.md
  testing-strategy.md
sample_app/
  app/
  tests/
workspace/runs/
evaluation/
  scenarios/
  reports/
tests/
  unit/
  graph/
  rag/
  mcp/
  integration/
  e2e/
scripts/
docs/
  architecture/
  diagrams/
  rag.md
  mcp.md
  evaluation.md
README.md
.env.example
```

### Dependency rules

1. `contracts` and `config` depend only on Python/Pydantic; they import no
   agent, adapter, graph, or framework implementation.
2. `models.context` creates `ContextEnvelope` projections from state and may
   depend only on contracts and prompt-rendering inputs.
3. Agents depend on contracts, context, prompt rendering, and abstract ports
   for LLM/RAG/MCP/observability. They do not import graph routers, concrete
   provider clients, or another agent.
4. `graph` depends on contracts, agents, guardrails, and injected ports.
   Routers are the sole owners of transition decisions.
5. `llm`, `rag`, `mcp`, `workspace`, and `observability` are adapter modules.
   They may depend on contracts/config/guardrails but never on `graph` or an
   agent implementation.
6. `guardrails` is shared policy infrastructure. It may validate contracts
   and configuration but cannot invoke an LLM or mutate the workspace.
7. `cli` is the composition root: it loads configuration, constructs adapters,
   compiles the graph, and invokes the run. It contains no business routing.
8. Tests may depend on production modules; production modules never depend on
   tests, `sample_app`, evaluation reports, or documentation.

## 2. Core contracts and state

### 2.1 Pydantic contract ownership

`contracts/enums.py` fixes the allowed values for roles, reviewer status,
security severity, remediation category, route target, tool status, and error
codes. `contracts/models.py` owns the following models:

| Contract | Required implementation fields and responsibility |
| --- | --- |
| `ProductSpecification` | objective, actors, business_rules, constraints, acceptance_criteria, nfrs, ambiguities, assumptions, and source requirement reference. |
| `ArchitectureProposal` | components, APIs, data_changes, integrations, dependencies, decisions, risks, impact, and RAG evidence references. |
| `ImplementationResult` | action mode (`PROPOSED` or `APPLIED`), changed_files, diff, evidence, validation_result, and security_surface_changed. |
| `SecurityFinding` | category, severity, description, affected evidence, recommendation, and source references. |
| `SecurityReview` | PASS/FAIL result, highest severity, findings, recommendations, sources, and `requires_hitl`. |
| `TestResult` | proposed_tests, generated_tests, executed_tests, actual_results, status, failures, coverage mapping, and evidence references. |
| `ReviewerDecision` | status, score, subscores, problems, reason, remediation_category, return_to recommendation, confidence, and evidence references. |
| `RetrievedEvidence` | source, section, version, chunk_id, fragment/reference, domain/query, score when supplied, and retrieval timestamp. |
| `ToolResult` | tool name, allowed role, status, input summary, output summary, duration, evidence reference, and normalized error. |
| `ModelExecutionInfo` | agent, provider, requested_model, actual_model, model_profile, fallback_used, fallback_reason, degraded, latency_ms, usage, and error. |
| `CloudFallbackContext` | agent, task, minimal relevant requirement, minimal structured input, validation error, relevant RAG fragments, relevant diff/code fragments, and deterministic evidence. |
| `WorkflowError` | code, source stage, retryable flag, detail safe for telemetry, evidence reference, and timestamp. |
| `FinalReport` | FEATURE, STATUS, REQUIREMENTS, ARCHITECTURE, SECURITY, TESTING, IMPLEMENTATION, RISK, ITERATIONS, DOCUMENTATION_USED, TOOLS_EXECUTED, MODELS_USED, ERRORS_DEGRADATIONS, TRACE_ID, and NEXT_ACTION. |

The LLM-related error code enum shall include exactly the mandated semantic
codes `LLM_AVAILABILITY_ERROR`, `LLM_QUALITY_ERROR`, `SECURITY_CONFLICT`,
`TOOL_ERROR`, `RAG_ERROR`, and `CLOUD_FALLBACK_UNAVAILABLE`, plus
`MCP_ERROR` and `AGENT_TIMEOUT` needed by the Spec. Invalid Pydantic output is
recorded as `LLM_QUALITY_ERROR`; it is never applied to state.

### 2.2 EngineeringState and ContextEnvelope

`contracts/state.py` defines `EngineeringState` with at least:

`run_id`, `requirement`, `specification`, `repository_context`, `architecture`,
`implementation`, `security_review`, `test_results`, `review`,
`rag_evidence`, `tool_results`, `model_usage`, `iteration`, `errors`,
`human_review_required`, and `final_status`.

It also keeps route-local fields required for deterministic execution:
`remediation_request`, `next_validation_path`, `cloud_escalations_by_agent`,
`cloud_escalations_run`, `local_retries_by_stage`, `local_repairs_by_stage`,
and `trace_id`. Reducers append evidence collections and replace singular
validated artifacts; nodes never mutate state in place.

`models/context.py` defines a `ContextEnvelope` with: agent identity, current
task, minimal state projection, relevant RAG evidence, relevant ToolResults,
remediation feedback, output-schema summary, allowed tools, and model profile.
It rejects unknown fields and records the projection fingerprint for context
isolation tests.

| Agent | Required inputs | Optional inputs | Explicitly prohibited context | Output |
| --- | --- | --- | --- | --- |
| Product | requirement, run_id, output schema | prior remediation feedback | repository files, diffs, security findings, complete state, credentials | ProductSpecification |
| Architecture | ProductSpecification, requirement, architecture RAG evidence | read-only repository summary, remediation feedback | write tools, full test output, secrets, full state | ArchitectureProposal |
| Developer | ProductSpecification, ArchitectureProposal, bounded repository context, relevant remediation feedback | SecurityReview/TestResult relevant to repair, developer RAG evidence | cloud keys, complete RAG corpus, hidden prompts, full state | ImplementationResult |
| Security | ProductSpecification, ArchitectureProposal, ImplementationResult, security RAG evidence, security ToolResults | relevant test result and remediation feedback | write tools, full repository, unrelated user data, secrets, full state | SecurityReview |
| Testing | ProductSpecification, ArchitectureProposal, ImplementationResult, testing RAG evidence, quality ToolResults | relevant SecurityReview and remediation feedback | write repository tools, unrelated security evidence, secrets, full state | TestResult |
| Reviewer | all validated stage summaries, provenance references, normalized ToolResults, model usage, iteration | remediation feedback | raw repository contents, direct tool permissions, credentials, full prompts | ReviewerDecision |

## 3. Agent and prompt architecture

Every agent implements a common port defined in `agents/base.py`:
`execute(envelope: ContextEnvelope) -> ValidatedAgentResult`. The result is
validated by the agent-specific Pydantic contract before the graph node can
merge it. An agent may recommend a remediation category; it cannot select a
node or model.

| Agent | Responsibility and RAG | Local profile/model | Cloud fallback | MCP allowlist | Failure behavior |
| --- | --- | --- | --- | --- | --- |
| Product | Turn a requirement into ProductSpecification; no RAG required unless product-policy corpus is later added. | `DEEP_MODEL` / `qwen3.5:9b` | Google `gemini-3.7-flash` | none | Schema/semantic failure uses one repair, then eligible cloud fallback; otherwise HUMAN_REVIEW_REQUIRED. |
| Architecture | Produce ArchitectureProposal grounded in architecture/API sources. | `FAST_MODEL` / `qwen3.5:4b` | Google `gemini-3.7-flash` | repository read-only: list_files, read_file, search_code, get_file_content | Schema/grounding repair once; if relevant RAG remains over budget after deterministic filtering/compression, use eligible cloud fallback. |
| Developer | Inspect isolated workspace and produce a concrete evidence-backed technical proposal or apply a bounded authorized change. A PROPOSED result names only inspected paths, includes a safe diff/pseudodiff, validation strategy, and explicit security-surface impact; an empty result requires a specific no-op justification. | `CODING_MODEL` / `qwen3.5:9b` | Groq `openai/gpt-oss-120b` | all Repository MCP tools; Quality MCP run_build, get_build_status, run_linter | Incorrect generated-code compile/lint/test outcome is repaired once; MCP/filesystem failure never triggers cloud. |
| Security | Evaluate required threat categories using security/OWASP RAG and scans. | `DEEP_MODEL` / `qwen3.5:9b` | Groq `openai/gpt-oss-120b` | Quality MCP scan_dependencies, run_security_scan, get_security_report | Scanner/RAG contradiction with PASS, ambiguous HIGH/CRITICAL, or Reviewer-detected omission becomes `SECURITY_CONFLICT` and uses cloud only as a second opinion. CRITICAL routes HITL. |
| Testing | Distinguish proposed/generated/executed tests and actual results using testing RAG. | `FAST_MODEL` / `qwen3.5:4b` | Groq `openai/gpt-oss-20b` | Quality MCP run_tests, get_test_results, run_build, get_build_status, run_linter | Generated test syntax/collection failure repairs once; a valid test finding a real application bug does not trigger cloud. |
| Reviewer | Score evidence and issue an approval/rejection recommendation. | `DEEP_MODEL` / `qwen3.5:9b` | Google `gemini-3.7-flash` | none | Invalid structure, low confidence, or material evidence contradiction repairs once then uses eligible cloud fallback; router validates result. |

Each agent has these two prompt assets only:

```text
prompts/<agent>/system.md
prompts/<agent>/user.md
```

`system.md` concisely declares role, responsibility, boundaries, evidence to
preserve, output contract, and that the role does not select routing or a
model. Deterministic decisions remain in graph/code rather than prompts.
`user.md` receives only task/current requirement, the envelope's relevant
state, necessary RAG evidence, relevant ToolResults, remediation feedback,
and output schema context. Prompt rendering refuses full-history injection.

## 4. LangGraph workflow and deterministic routers

`graph/stategraph.py` builds the real `StateGraph`; `graph/nodes.py` contains
one node adapter per agent plus FinalReport and HITL nodes; `graph/routers.py`
contains pure deterministic routing functions. No conditional edge calls an
LLM.

### 4.1 Normal path

```text
START → Product → Architecture → Developer → Security → Testing → Reviewer
Reviewer APPROVED → FinalReport → END
```

Every node first validates its inbound state and context projection, invokes
the model/tool ports, validates output, appends traces/evidence, and returns a
state patch. Error routers run after every node.

### 4.2 Review and remediation routing

The Reviewer can emit a recommendation only. `validate_reviewer_decision`
checks status, remediation category, allowed `return_to`, required evidence,
and iteration budget before `review_router` chooses an edge.

| Validated remediation category | Entry node | Required continuation |
| --- | --- | --- |
| Architecture issue | Architecture | Architecture → Developer → Security → Testing → Reviewer |
| Implementation issue | Developer | Developer → Security → Testing → Reviewer |
| Security issue requiring code | Developer | Developer → Security → Testing → Reviewer |
| Testing issue caused by implementation | Developer | Developer → Testing → Reviewer, marked `testing_only` unless Developer reports security-surface change |
| Developer change alters security surface | Developer | Developer → Security → Testing → Reviewer |

The router increments `iteration` exactly once when it accepts a rejected
Reviewer decision and enters one of these remediation paths, never per node.
At `iteration == 3`, another rejection routes directly to
`HUMAN_REVIEW_REQUIRED` and stops automatic routing. `SecurityReview` with
highest severity `CRITICAL` routes directly to the `security_hitl` node before
Reviewer. The HITL node records a human decision, then either resumes the
predefined allowed route or terminates; it cannot introduce a new route.

### 4.3 Error routing policy

- `LLM_AVAILABILITY_ERROR`, unavailable local model, timeout, or transient
  transport failure: consume one `MAX_LOCAL_RETRIES` retry; after another
  failure, use eligible cloud fallback only if cloud is enabled and budgeted.
- `LLM_QUALITY_ERROR` (invalid Pydantic output, incomplete output, failed
  semantic validation): consume one `MAX_LOCAL_REPAIRS` reformulation/repair;
  then use eligible cloud fallback only if the role trigger permits it.
- `SECURITY_CONFLICT`: obtain the configured Security cloud second opinion if
  enabled and budgeted; CRITICAL status still routes HITL.
- `MCP_ERROR`, `TOOL_ERROR`, `RAG_ERROR`, filesystem error, and a real
  application test failure use their dedicated remediation/error path and
  never activate cloud automatically.
- Cloud output is validated exactly as local output. Unavailable cloud records
  `CLOUD_FALLBACK_UNAVAILABLE`, marks degraded execution, and routes to
  `HUMAN_REVIEW_REQUIRED` when the required stage cannot complete locally.

## 5. Model registry, deterministic routing, and cloud privacy

`llm/registry.py` reads external configuration only:

```text
FAST_MODEL=qwen3.5:4b
DEEP_MODEL=qwen3.5:9b
CODING_MODEL=qwen3.5:9b
LOCAL_FIRST=true
MAX_LOCAL_RETRIES=1
MAX_LOCAL_REPAIRS=1
MAX_CLOUD_ESCALATIONS_PER_AGENT=1
MAX_CLOUD_ESCALATIONS_PER_RUN=3
GEMINI_API_KEY=
GROQ_API_KEY=
```

`.env.example` exposes the two key names with empty values. Configuration
defaults cloud enablement to false, so neither paid use nor outbound cloud
traffic occurs unless explicitly enabled.

`llm/router.py` accepts `(agent_role, validated_failure_context)` and returns
a `ModelSelection`; it is the only model-selection authority. Mapping is:

| Role | Model profile | Local provider/tag | Cloud provider/model |
| --- | --- | --- | --- |
| Product | DEEP_MODEL | Ollama `qwen3.5:9b` | Google `gemini-3.7-flash` |
| Architecture | FAST_MODEL | Ollama `qwen3.5:4b` | Google `gemini-3.7-flash` |
| Developer | CODING_MODEL | Ollama `qwen3.5:9b` | Groq `openai/gpt-oss-120b` |
| Security | DEEP_MODEL | Ollama `qwen3.5:9b` | Groq `openai/gpt-oss-120b` |
| Testing | FAST_MODEL | Ollama `qwen3.5:4b` | Groq `openai/gpt-oss-20b` |
| Reviewer | DEEP_MODEL | Ollama `qwen3.5:9b` | Google `gemini-3.7-flash` |

`llm/ollama.py` and `llm/cloud.py` implement the same structured-generation
port. Each invocation creates `ModelExecutionInfo` and records requested vs.
actual model, latency in milliseconds, usage when supplied, fallback state,
degradation, and a safe error summary.

`CloudFallbackContext` is built by a dedicated sanitizer. It includes only
the target agent, task, relevant requirement, minimum structured inputs,
validation failure, selected RAG fragments, selected diff/code fragments, and
deterministic evidence. It rejects `.env`, API keys, secret values, complete
repository snapshots, complete EngineeringState, and unrelated context before
the provider adapter is called.

## 6. RAG design

`knowledge/` starts with six real source documents named in the structure
above. The retrieval pipeline is fixed as:

```text
source documents → LangChain Document → LangChain RecursiveCharacterTextSplitter
→ Sentence Transformers → Chroma → domain-filtered retriever
→ RetrievedEvidence → ContextEnvelope → Agent
```

Initial Plan-frozen parameters are `chunk_size=800` tokens,
`chunk_overlap=160` tokens (20%), `top_k=4`, `fetch_k=8` when MMR is enabled,
and `RAG_MIN_RELEVANCE=0.55` on the normalized retriever score. All are
external configuration values; evaluation may recalibrate them only through a
subsequent SDD change. The embedding baseline is
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: it supports
Spanish and English guidance locally with low runtime cost, matching the
local-first requirement.

Each chunk carries `domain`, `source`, `section`, `version`, and `chunk_id`.
Retrievers apply domain filters: Architecture (`architecture`, `api`), Security
(`security`, `owasp`), and Testing (`testing`, `coding`). They request MMR
with `fetch_k=8`, retain only top four above relevance, and return
`NO_RELEVANT_DOCS` plus `RAG_ERROR` when none survive. No agent may generate
a citation unless the source is present in `RetrievedEvidence` or explicitly
provided user context.

## 7. MCP, workspace, and guardrails

`mcp/contracts.py` normalizes all calls as validated `ToolResult` values with
input/output summaries, timeout, duration, status, and safe error. The locked
runtime boundary is LangGraph/agent → synchronous MCP client adapter → official
MCP client session over stdio → real Repository or Quality MCP Server → bounded
existing backend service. Each server call is checked by
`mcp/permissions.py` and `workspace/paths.py` before execution. Repository and
Quality retain independent tool surfaces and permissions even if they share
server bootstrap infrastructure. Direct backend calls remain unit-testable but
do not count as primary protocol evidence.

| MCP server | Permitted operations | Roles |
| --- | --- | --- |
| Repository MCP | list_files, read_file, search_code, get_file_content | Architecture (read-only), Developer |
| Repository MCP | create_file, update_file, get_diff | Developer only |
| Quality MCP | run_build, get_build_status, run_linter | Developer, Testing |
| Quality MCP | run_tests, get_test_results | Testing only |
| Quality MCP | scan_dependencies, run_security_scan, get_security_report | Security only |

Every tool schema validates arguments, uses configurable timeout, denies
unknown operations, resolves the path inside the run copy, rejects `..` and
external roots, redacts secrets in summaries, and preserves failure results.
`ToolResult` has real graph consequences: a failed `run_tests` produces a
failed `TestResult`, then Reviewer rejection and remediation; an unavailable
MCP produces `MCP_ERROR` without cloud escalation.

`workspace/isolation.py` creates one copy of `sample_app/` under
`workspace/runs/<run_id>/` per run. Destructive operations require explicit
authorization recorded in the state and are not inferred from an LLM output.

## 8. Observability, evaluation, and reporting

`observability/langfuse.py` creates one root trace per `run_id` and child
spans for model selection, all six agents, prompt metadata, RAG retrieval,
documents/chunks, every MCP call, validation, routing, retry, repair, cloud
fallback, remediation, HITL, FinalReport, and errors. Prompt and payload
recorders use the secret redactor before export.

`observability/metrics.py` derives, only from completed evaluation records and
Langfuse evidence: average duration, LLM calls, iterations, tokens/usage when
available, tool calls, retrievals, APPROVED/REJECTED counts, latency by agent,
latency by model, fallback count/rate, error counts by type, structured-output
success/failure, expected-vs-observed status, and final outcome. Missing
provider usage is reported as unavailable rather than estimated.

`observability/evaluation.py` preserves the fast deterministic mode and adds an
explicit LIVE mode that runs SC-01 through SC-05 through the real local
`ModelRouter` and `LocalModelRuntime`. LIVE records and aggregates are written
separately, contain non-zero LLM calls and measured agent/model latencies, and
never overwrite deterministic evidence. It also produces a multi-model
comparison grouped by `(agent, actual_model)`. The local bonus acceptance run
must contain all six agent spans and actual successful spans for both
`qwen3.5:4b` and `qwen3.5:9b`; cloud spans are labelled contingency and are
excluded from this proof.

## 9. Sample application and five scenario execution

Create a minimal FastAPI/SQLite application only when no existing target app
is available. It contains a local testable authentication boundary, password
reset tokens with expiry and single-use state, failed-login lock counter, and
authenticated transaction history scoped by owner and limited to five rows.
It is intentionally minimal and is copied per run; it is not a seventh agent
or a product UI.

Evaluation cases are fixed:

| Scenario | Expected outcome | Observable focus |
| --- | --- | --- |
| SC-01 Password Recovery | APPROVED | 15-minute, single-use token. |
| SC-02 Account Locking | APPROVED | Lock after exactly five failed attempts. |
| SC-03 Transaction History API | APPROVED | Authorized ownership and maximum five transactions. |
| SC-04 Non-expiring password reset token | REJECTED | Security flags unsafe lifetime. |
| SC-05 Transactions by arbitrary ID | REJECTED | Security flags authorization/IDOR. |

SC-04 and SC-05 are evaluated requirements and must be rejected without
creating an intentionally vulnerable sample-app implementation.

## 10. Documentation deliverables

Implementation Tasks must produce:

- `README.md`: purpose, architecture, stack, installation, configuration,
  execution, environment variables, required Ollama models, optional cloud
  configuration, and reproducible demo commands.
- `docs/architecture/`: module boundaries, dependency direction, contracts,
  and ContextEnvelope matrix.
- `docs/diagrams/architecture.md`: User → LangGraph → Agents → RAG/MCP →
  External Systems → Langfuse diagram.
- `docs/diagrams/langgraph.md`: nodes, normal/conditional edges, loops, error
  routes, both mandated HITL routes, and termination.
- `docs/rag.md`: corpus, loaders, fixed Plan parameters, embedding rationale,
  Chroma, filters, relevance, provenance, and NO_RELEVANT_DOCS behavior.
- `docs/mcp.md`: servers, schemas, role permissions, least privilege, error
  handling, and the ToolResult-to-routing example.
- `docs/evaluation.md`: five cases, expected vs. observed, scores, aggregate
  metrics, multi-model comparison, errors/fallbacks, and trace IDs.

HITL documentation must separately explain the location, trigger, human
rationale, mitigated risk, human input, and resume/termination behavior for:
Security `CRITICAL` and the third unapproved remediation cycle.

## 11. Implementation work packages for Tasks

Each work package has a reviewable, independently testable boundary. Later
Tasks must retain this order and must not redesign its interfaces.

### Task 1: Project foundation and configuration

**Files:** create package markers, `config.py`, `cli.py`, `.env.example`, and
configuration tests.

- [ ] Define externally loaded model IDs, policy limits, provider switches,
  timeouts, RAG parameters, and workspace root.
- [ ] Set cloud execution and paid use disabled by default.
- [ ] Implement CLI input validation, `run_id` allocation, and composition
  root without routing logic.
- [ ] Test Python version guard, defaults, missing cloud keys, and safe config
  redaction.

### Task 2: Pydantic contracts and state reducers

**Files:** create `contracts/enums.py`, `contracts/models.py`,
`contracts/state.py`, and unit tests.

- [ ] Implement every contract in Section 2 with strict enums and forbidden
  extra fields.
- [ ] Define append/replace reducers and invariant checks for EngineeringState.
- [ ] Test valid/invalid statuses, enum rejection, all FinalReport fields, and
  state evidence preservation.

### Task 3: Guardrails, context projections, and prompts

**Files:** create `models/context.py`, `guardrails/*.py`, all twelve prompt
files, and focused tests.

- [ ] Render separate system/user prompts from ContextEnvelope only.
- [ ] Enforce secret blocking, context isolation, allowed route validation,
  timeout policy, and output validation before state merge.
- [ ] Test prohibited context omissions, prompt separation, path traversal,
  secret leakage blocking, and invalid structured output.

### Task 4: Local LLM registry, router, and repair semantics

**Files:** create `llm/registry.py`, `llm/router.py`, `llm/ollama.py`,
`llm/repair.py`, and unit tests.

- [ ] Implement the fixed role-to-profile mapping without agent-side model IDs.
- [ ] Persist ModelExecutionInfo for all attempts and distinguish retry from
  repair counters.
- [ ] Test 4B/9B routing, Security DEEP profile, unavailable local model,
  timeout retry, invalid output repair, and limit boundaries.

### Task 5: Cloud fallback adapter and privacy boundary

**Files:** create `llm/cloud.py`, extend guardrails, and tests.

- [ ] Implement fixed Google/Groq fallback mapping and per-role trigger rules.
- [ ] Build and validate CloudFallbackContext before a provider call.
- [ ] Test missing keys, disabled paid use, sanitization, one escalation per
  agent, three per run, cloud outage, and no cloud for MCP/RAG/tool failures.

### Task 6: RAG ingestion, Chroma index, and specialized retrieval

**Files:** create six knowledge documents and `rag/*.py`, plus RAG tests.

- [ ] Implement loaders, token-aware chunks, configured embeddings/index, and
  metadata preservation.
- [ ] Implement Architecture/Security/Testing domain filters, MMR retrieval,
  relevance filtering, and NO_RELEVANT_DOCS result.
- [ ] Test provenance fields, Spanish/English retrieval, score threshold,
  specialization, and no invented citation.

### Task 7: Workspace isolation and MCP adapters

**Files:** create `workspace/*.py`, `mcp/*.py`, and MCP tests.

- [ ] Implement isolated sample-app copy and resolved-path enforcement.
- [ ] Implement validated Repository/Quality tool contracts and role allowlists.
- [ ] Test every required operation, denied writes, MCP unavailable, tool
  timeout, ToolResult retention, destructive authorization, and traversal
  rejection.

### Task 8: Six agent implementations

**Files:** create `agents/base.py` and one module per agent, plus unit tests.

- [ ] Construct one ContextEnvelope per role and invoke only permitted ports.
- [ ] Validate outputs against the exact contracts and preserve declared
  evidence, tool results, RAG sources, and failure states.
- [ ] Test responsibility boundaries, required output fields, prohibited tool
  access, and each agent-specific cloud trigger.

### Task 9: StateGraph nodes, routers, and HITL

**Files:** create `graph/stategraph.py`, `graph/nodes.py`, `graph/routers.py`,
`graph/hitl.py`, and graph tests.

- [ ] Compile normal edges, conditional edges, FinalReport node, and both HITL
  outcomes.
- [ ] Implement validated Reviewer remediation mapping, iteration accounting,
  error paths, and no direct LLM routing.
- [ ] Test valid/invalid route targets, every remediation chain,
  MAX_ITERATIONS, CRITICAL HITL, human resume/termination, and failed-test to
  Reviewer rejection to remediation.

### Task 10: Langfuse observability and reporting

**Files:** create `observability/*.py` and integration tests.

- [ ] Emit one root trace and required spans/events while redacting secrets.
- [ ] Aggregate only real run/trace metrics and label unavailable usage.
- [ ] Test trace correlation, retries/repairs, fallback, tool/RAG telemetry,
  latency aggregation, and model comparison fields.

### Task 11: Minimal sample app and evaluation harness

**Files:** create `sample_app/`, `evaluation/scenarios/`, evaluation modules,
and integration/E2E tests.

- [ ] Implement only the safe FastAPI/SQLite functionality needed by SC-01 to
  SC-03 and fixtures representing SC-04/SC-05 requirement inputs.
- [ ] Execute every scenario against an isolated run copy.
- [ ] Test exact five scenarios, two REJECTED outcomes, required scenario
  fields, score dimensions, and real failed-test remediation flow.

### Task 12: E2E multi-model bonus evidence and documentation

**Files:** create documentation deliverables in Section 10, scripts, and E2E
tests.

- [ ] Run a normal local E2E evaluation with all six agents and both local
  model tags.
- [ ] Generate the evaluation report, multi-model comparison, Langfuse trace
  evidence, diagrams, RAG/MCP docs, and reproducible README commands.
- [ ] Test documentation completeness, demo command reproducibility, and that
  cloud spans do not satisfy multi-model acceptance evidence.

## 12. Verification matrix and acceptance gates

| Requirement group | Primary work package | Acceptance evidence |
| --- | --- | --- |
| FR-001–020, NFR-005, NFR-010 | 2, 3, 9 | StateGraph inspection, routing/HITL/iteration tests, trace. |
| FR-021–034, NFR-006 | 3, 8 | Context isolation, contract and responsibility tests. |
| FR-035–040, FR-074, NFR-008 | 6, 12 | Corpus inventory, provenance/relevance tests, RAG documentation. |
| FR-041–045, NFR-011–013, NFR-018 | 7, 9 | MCP contracts, sandbox tests, ToolResult routing trace. |
| FR-046–059, FR-076–077, NFR-007, NFR-009, NFR-017 | 1, 4, 5, 12 | Deterministic mappings, local 4B/9B run, cloud policy tests. |
| FR-060–073, FR-075, NFR-014–016 | 9, 10, 11 | Langfuse trace, error-path tests, reports and five scenarios. |
| FR-078–086 | 12 | README, diagrams, RAG/MCP/evaluation/HITL docs and demo transcript. |

The final gate runs unit, graph, RAG, MCP, integration, and E2E suites; it
requires exactly five scenario records, exactly two expected rejections, a
local all-six-agent trace using both model tags, and no missing required
evidence. Documentation validation is a proportional gate and does not add
artificial product tests.

## 13. Architectural risks and mitigations

| Risk | Mitigation locked by this plan |
| --- | --- |
| Required Ollama tags unavailable or too slow | Record availability/degradation, use one retry then governed fallback/HITL; never silently substitute a model. |
| Cloud keys absent or cloud outage | Preserve local-first execution; record unavailability, do not expose key details, and escalate only when the stage cannot complete. |
| LLM hallucination or invalid JSON | Pydantic validation, one role-bounded repair, provenance checks, and deterministic routers. |
| Unsafe workspace operation | Run-copy isolation, role allowlists, resolved-path checks, destructive authorization, and secret redaction. |
| RAG grounding is weak | Domain metadata filters, calibrated relevance, NO_RELEVANT_DOCS, and Reviewer rejection of unsupported conclusions. |
| Cost/privacy leakage | Explicit cloud enablement, minimal CloudFallbackContext, redaction, and no whole-repository/state export. |

## 14. Plan self-review

- All 86 FRs and 18 NFRs map to one or more work packages in Section 12.
- The local 4B/9B multi-model evaluation is the only bonus and is isolated
  from the cloud contingency policy.
- Model selection belongs only to registry/router; no agent controls it.
- Transitions belong only to deterministic routers; Reviewer recommendations
  are validated before use.
- The retry/recovery distinction, fallback privacy, RAG parameters, MCP
  permissions, evidence, documentation, demo, and both HITL routes are fixed.
- No plan, task, code, test, or documentation artifact other than this plan is
  created by the present change.
