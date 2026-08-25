# Feature Specification: Autonomous Engineering Team

**Feature ID:** 001-autonomous-engineering-team  
**Status:** Ready for Plan  
**Governing document:** `.specify/memory/constitution.md`

## 1. Purpose

The system shall accept one functional requirement and coordinate a governed
software-engineering workflow across exactly six specialized agents: Product,
Architecture, Developer, Security, Testing, and Reviewer. The workflow shall
produce an evidence-backed final decision and shall support deterministic
remediation, error handling, Human-in-the-Loop (HITL), RAG, MCP, structured
outputs, local multi-model execution, and end-to-end observability.

This specification defines required behavior and quality attributes. It does
not prescribe classes, source files, functions, or detailed implementation.

## 2. Actors and boundaries

- **User:** submits a functional requirement and, when requested, supplies a
  HITL decision.
- **Six core agents:** Product, Architecture, Developer, Security, Testing,
  and Reviewer, each with non-overlapping responsibility.
- **External systems:** local Ollama models, optional cloud model providers,
  the RAG corpus, Repository MCP, Quality MCP, and Langfuse.
- **System boundary:** the authorized repository workspace and the data
  required to process one run.

## 3. Assumptions

- At least five real, non-placeholder documents will be made available to the
  RAG corpus before acceptance evaluation.
- Cloud credentials may be absent; local execution remains the baseline.
- A user is available only when a route explicitly reaches HITL or
  `HUMAN_REVIEW_REQUIRED`.
- Model identifiers, credentials, timeouts, and policy limits are supplied by
  external configuration and are not embedded in agent prompts.

## 4. Functional requirements

Each requirement names the minimum evidence by which it shall be verified.

### 4.1 Run lifecycle, orchestration, and shared state

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-001 | The system SHALL accept one functional requirement through a CLI invocation. | CLI transcript containing the submitted requirement. |
| FR-002 | The system SHALL assign a unique `run_id` to every accepted requirement. | Final state and trace containing the same unique `run_id`. |
| FR-003 | The system SHALL execute exactly six core agent roles named Product, Architecture, Developer, Security, Testing, and Reviewer. | Trace containing exactly these six core role names. |
| FR-004 | A normal successful run SHALL visit Product, Architecture, Developer, Security, Testing, and Reviewer in that order. | Ordered agent spans in the trace. |
| FR-005 | The workflow SHALL execute as a real LangGraph `StateGraph` with multiple nodes rather than as a manual chain of model calls. | Graph inspection and E2E trace showing distinct nodes. |
| FR-006 | The shared `EngineeringState` SHALL preserve `run_id`, `requirement`, `specification`, `repository_context`, `architecture`, `implementation`, `security_review`, `test_results`, `review`, `rag_evidence`, `tool_results`, `model_usage`, `iteration`, `errors`, `human_review_required`, and `final_status`. | Serialized state contract and completed-run snapshot. |
| FR-007 | Each agent SHALL receive only the subset of `EngineeringState` required for its declared responsibility. | Per-agent input snapshots with an isolation assertion. |
| FR-008 | Every agent invocation SHALL contain a distinct system prompt and user prompt. | Redacted prompt metadata in the trace. |
| FR-009 | Every agent output that can affect state, routing, approval, remediation, or escalation SHALL pass Pydantic validation before use. | Validation result attached to each decision-affecting output. |
| FR-010 | The graph SHALL contain normal edges for the successful progression between agent stages. | Graph inspection showing normal edges. |
| FR-011 | The graph SHALL contain conditional edges for review, error, remediation, and HITL outcomes. | Graph inspection plus traces exercising conditional edges. |
| FR-012 | The graph SHALL contain at least one executable remediation loop from Reviewer to a responsible agent and back through required validation. | A rejected-run trace containing a repeated agent stage. |
| FR-013 | `Reviewer.status=APPROVED` SHALL set `final_status=APPROVED` and terminate the run. | Approved trace ending immediately after the terminal route. |
| FR-014 | `Reviewer.status=REJECTED` SHALL trigger a validated conditional route to the responsible agent identified by `return_to`. | Rejected trace containing recommendation, validation, and selected route. |
| FR-015 | A `return_to` value outside the allowed remediation routes SHALL be rejected and SHALL NOT be executed. | Negative route-validation result and recorded error. |
| FR-016 | `iteration` SHALL increase exactly once when a rejected review begins a new remediation cycle. | State history across a remediation loop. |
| FR-017 | The workflow SHALL permit no more than `MAX_ITERATIONS=3` remediation cycles. | Boundary test covering iterations 1 through 3. |
| FR-018 | A third failed remediation cycle SHALL set `human_review_required=true`, set `final_status=HUMAN_REVIEW_REQUIRED`, and terminate automated routing. | Three-cycle trace and final state. |
| FR-019 | A Security finding with severity `CRITICAL` SHALL route to HITL before any approval or further automated remediation. | Security-to-HITL conditional-route trace. |
| FR-020 | A HITL route SHALL pause automated progress until an explicit human decision is recorded. | Pause/resume trace with human-decision evidence. |

### 4.2 Agent responsibilities and outputs

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-021 | Product SHALL produce a structured specification containing objective, actors, business rules, constraints, acceptance criteria, non-functional requirements, ambiguities, and assumptions. | Validated Product output containing every named field. |
| FR-022 | Architecture SHALL produce components, APIs, data changes, integrations, dependencies, decisions, risks, impact, and RAG evidence/sources. | Validated Architecture output and linked retrieval evidence. |
| FR-023 | Developer SHALL consume the validated Product specification and Architecture output for the current run. | Developer input evidence referencing both artifacts. |
| FR-024 | Developer SHALL inspect actual context from the authorized workspace before proposing or applying a change and SHALL produce a concrete technical proposal grounded in inspected files; an empty proposal is permitted only with a specific evidence-backed no-op justification. | Repository tool evidence preceding a non-empty Developer proposal or its explicit no-op justification. |
| FR-025 | Developer SHALL use Repository MCP through a real Model Context Protocol client/server session for repository inspection and authorized workspace changes. | Protocol-level Repository MCP calls linked to the Developer span. |
| FR-026 | Developer SHALL distinguish whether its result only proposes changes or applies authorized changes. | Explicit action mode in the validated Developer output. |
| FR-027 | Developer SHALL preserve `changed_files`, `diff`, `evidence`, and `validation_result` in its structured output. | Validated Developer output containing every named field. |
| FR-028 | Security SHALL evaluate authentication, authorization, input validation, sensitive information, secrets, injection, access control, IDOR, secure logging, data protection, API abuse, rate limiting, and applicable OWASP risks. | Security checklist with a result for every category. |
| FR-029 | Security SHALL output `PASS` or `FAIL`, severity, findings, recommendations, and sources. | Validated Security output containing every named field. |
| FR-030 | Testing SHALL cover happy path, error behavior, edge cases, validation, security, and business rules. | Test coverage matrix mapped to the requirement. |
| FR-031 | Testing SHALL report proposed tests, generated tests, executed tests, and actual results as four distinct categories. | Validated Testing output containing all four categories. |
| FR-032 | Reviewer SHALL evaluate requirements completeness, architecture correctness, implementation consistency, security, testing, internal standards, RAG grounding, and MCP evidence. | Reviewer evaluation matrix containing every dimension. |
| FR-033 | Reviewer SHALL output `status`, `score`, `subscores`, `problems`, `reason`, `remediation_category`, `return_to`, and `confidence`. | Validated Reviewer output containing every named field. |
| FR-034 | Reviewer SHALL only recommend `return_to`; LangGraph SHALL validate the recommendation before routing. | Reviewer output plus independent route-validation evidence. |

### 4.3 RAG and provenance

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-035 | The RAG corpus SHALL contain at least five real, non-placeholder documents. | Corpus inventory with five or more source identifiers. |
| FR-036 | Retrieval SHALL execute the observable sequence source documents → LangChain `Document` abstraction → LangChain text splitting → Sentence Transformers → Chroma → Specialized Retriever → RetrievedEvidence → Agent. | Retrieval trace and integration test containing each ordered stage and the concrete LangChain component. |
| FR-037 | Every `RetrievedEvidence` item SHALL contain `source`, `section`, `chunk_id`, `fragment/reference`, `domain/query`, and `score` when the retriever supplies one. | Validated retrieval output. |
| FR-038 | Architecture, Security, and Testing SHALL each have retrieval specialized for its own domain and query. | Three agent-specific retrieval traces. |
| FR-039 | A retrieval with no relevant evidence SHALL return `NO_RELEVANT_DOCS`. | Empty-retrieval test and state result. |
| FR-040 | No agent SHALL cite or create a source that is absent from retrieved evidence or explicitly supplied context. | Citation-to-source integrity check. |

### 4.4 MCP tools and operational evidence

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-041 | A real Repository MCP Server SHALL expose `list_files`, `read_file`, `search_code`, `get_file_content`, `create_file`, `update_file`, and `get_diff` through the official Model Context Protocol, and the workflow SHALL consume it through a real MCP client session. | Server capability discovery and real protocol session tests. |
| FR-042 | A real Quality MCP Server SHALL expose `run_tests`, `get_test_results`, `run_build`, `get_build_status`, `run_linter`, `scan_dependencies`, `run_security_scan`, and `get_security_report` through the official Model Context Protocol, and the workflow SHALL consume it through a real MCP client session. | Server capability discovery and real protocol session tests. |
| FR-043 | Each agent SHALL be restricted to an explicit least-privilege allowlist of MCP operations. | Per-agent permission matrix and denied-operation tests. |
| FR-044 | Every MCP result SHALL be preserved in `tool_results` and SHALL affect an applicable state field, validation, or routing decision. | Tool-result-to-state/route correlation. |
| FR-045 | The system SHALL demonstrate LangGraph → real MCP client/session → MCP Server → `run_tests=FAILED` → `TestResult=FAIL` → `Reviewer=REJECTED` → remediation. | E2E trace of the complete protocol-backed failure chain. |

### 4.5 Multi-model local bonus and cloud contingency

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-046 | A deterministic model-routing policy SHALL read model IDs from external configuration and SHALL prevent agents from selecting or hardcoding their own model. | Configuration snapshot and model-routing decision record. |
| FR-047 | The initial local assignment SHALL be Product=`qwen3.5:9b`, Architecture=`qwen3.5:4b`, Developer=`qwen3.5:9b`, Security=`qwen3.5:9b`, Testing=`qwen3.5:4b`, and Reviewer=`qwen3.5:9b`. | Per-agent requested/actual model records. |
| FR-048 | One normal E2E run SHALL demonstrate actual use of both `qwen3.5:4b` and `qwen3.5:9b`. | Single trace containing successful spans for both model tags. |
| FR-049 | Each model invocation SHALL record `agent`, `provider`, `requested_model`, `actual_model`, `model_profile`, `fallback_used`, `fallback_reason`, `degraded`, `latency`, `usage` when available, and `error`. | Validated `model_usage` entries. |
| FR-050 | Model execution SHALL apply the `LOCAL_FIRST` policy before considering cloud fallback. | Invocation sequence showing local attempt before cloud. |
| FR-051 | An agent SHALL receive at most `MAX_LOCAL_REPAIRS=1` local repair attempt after a correctable response-quality failure, including invalid structured output, Pydantic validation failure, incomplete response, or `LLM_QUALITY_ERROR`. | Boundary test with quality-failure attempt counts. |
| FR-052 | An agent SHALL receive at most `MAX_CLOUD_ESCALATIONS_PER_AGENT=1` cloud escalation per run. | Per-agent escalation counter evidence. |
| FR-053 | A run SHALL permit at most `MAX_CLOUD_ESCALATIONS_PER_RUN=3` cloud escalations. | Run-level escalation counter boundary test. |
| FR-054 | Cloud fallback SHALL map Product, Architecture, and Reviewer to `gemini-3.7-flash`; Developer and Security to `openai/gpt-oss-120b` via Groq; and Testing to `openai/gpt-oss-20b` via Groq. | Deterministic fallback-routing records for all roles. |
| FR-055 | Cloud fallback SHALL be eligible only for `LLM_AVAILABILITY_ERROR`, `LLM_QUALITY_ERROR`, or applicable `SECURITY_CONFLICT`, after the permitted local retry for availability or local repair for response quality. | Trigger-policy tests for allowed causes. |
| FR-056 | `TOOL_ERROR`, `MCP_ERROR`, and `RAG_ERROR` SHALL retain their own error paths and SHALL NOT trigger cloud fallback automatically. | Negative fallback-policy tests. |
| FR-057 | If cloud credentials are absent, the local workflow SHALL remain executable and SHALL report cloud fallback as unavailable without exposing credential details. | Local-only E2E run with no cloud credentials. |
| FR-058 | The system SHALL require explicit enablement before any cloud call that may incur paid usage. | Disabled-by-default configuration test and blocked-call evidence. |
| FR-059 | A cloud request SHALL exclude `.env`, API keys, secrets, the complete repository, the complete `EngineeringState`, and information unnecessary for the target agent. | Redacted outbound-payload inspection. |

### 4.6 Observability, errors, evaluation, and final output

| ID | Requirement | Required evidence |
| --- | --- | --- |
| FR-060 | Every accepted requirement SHALL create one Langfuse root trace correlated by `run_id`. | Trace lookup by `run_id`. |
| FR-061 | The root trace SHALL expose prompts, responses, agents, requested and actual models, provider, RAG retrievals, documents/chunks, MCP calls/results, latency, tokens/usage when available, fallback, errors, retries, iterations, HITL, and final result. | Trace completeness assertion. |
| FR-062 | An unavailable LLM invocation SHALL record `LLM_AVAILABILITY_ERROR`, apply at most one local retry, and then follow the eligible fallback policy or end as `HUMAN_REVIEW_REQUIRED` when no eligible execution path remains. | Unavailable-LLM fault-injection trace. |
| FR-063 | An unavailable configured local model SHALL record the requested and actual model outcome, mark the invocation degraded, and apply the same bounded availability policy as FR-062. | Missing-local-model fault-injection trace. |
| FR-064 | An unavailable eligible cloud fallback SHALL record the cloud error, stop further cloud attempts for that agent, and route to `HUMAN_REVIEW_REQUIRED` when the agent cannot complete locally. | Cloud-outage fault-injection trace. |
| FR-065 | An unavailable MCP SHALL record `MCP_ERROR`, avoid cloud escalation, and route to remediation or `HUMAN_REVIEW_REQUIRED` according to whether the missing result is required for approval. | MCP-outage fault-injection trace. |
| FR-066 | `NO_RELEVANT_DOCS` SHALL record a `RAG_ERROR`, prevent invented sources, and cause Reviewer to reject any conclusion whose required grounding is absent. | Empty-retrieval trace and Reviewer result. |
| FR-067 | A failed tool call SHALL record `TOOL_ERROR`, preserve the failed result, and route to bounded remediation without automatic cloud escalation. | Tool-failure fault-injection trace. |
| FR-068 | Invalid structured agent output, including Pydantic validation failure, SHALL be rejected before state mutation, recorded as `LLM_QUALITY_ERROR`, and receive at most one local repair before an eligible bounded fallback. | Schema-validation fault-injection trace. |
| FR-069 | An agent timeout SHALL cancel the timed-out attempt, record `AGENT_TIMEOUT`, preserve completed evidence, and follow the bounded local retry and availability policy. | Timeout fault-injection trace. |
| FR-070 | The final output SHALL be a `FinalReport` containing FEATURE, STATUS, REQUIREMENTS, ARCHITECTURE, SECURITY, TESTING, IMPLEMENTATION, RISK, ITERATIONS, DOCUMENTATION USED, TOOLS EXECUTED, MODELS USED, ERRORS / DEGRADATIONS, TRACE ID, and NEXT ACTION. | Validated FinalReport containing every named field. |
| FR-071 | The evaluation suite SHALL define and execute exactly the five scenarios SC-01 through SC-05 in Section 7, preserving a fast deterministic mode and providing a reproducible LIVE mode that invokes the real local ModelRouter and LocalModelRuntime. | Deterministic manifest plus five separate LIVE result records with local model calls. |
| FR-072 | Every scenario result SHALL preserve `expected_status`, `observed_status`, `status_match`, `expected_security_signal`, `observed_findings`, `reviewer_score`, `iterations`, `models_used`, `rag_sources`, `tools_used`, `trace_id`, and `pass`. | Validated result for each scenario. |
| FR-073 | Every scenario SHALL report scores for Requirements completeness, Architecture correctness, Security compliance, Testing completeness, Implementation consistency, and RAG grounding. | Scenario evaluation records containing all six dimensions. |
| FR-074 | The RAG documentation SHALL define and technically justify the chunking strategy, chunk size, overlap, embedding model, vector database, retrieval count/top_k, relevance criterion, specialized retrievers or metadata filters, and `NO_RELEVANT_DOCS` policy; parameters SHALL be externally configurable when applicable, and this requirement SHALL NOT fix their concrete values. | Versioned RAG documentation, configuration evidence where applicable, and a justification review. |
| FR-075 | The LIVE evaluation report SHALL derive from real local-model executions and Langfuse evidence an aggregate report containing average duration, average LLM calls greater than zero, average iterations, average tokens/usage when providers expose it, average tool calls, average retrievals, APPROVED count, REJECTED count, latency by agent, latency by model, cloud fallback count/rate, structured-output success/failure, and errors grouped by type; unavailable metrics SHALL be reported as unavailable and SHALL NOT be invented. | Separate LIVE aggregate report linked to five LIVE scenario records and Langfuse traces. |
| FR-076 | Multi-model evaluation SHALL compare, for each model/agent combination, the model used, agent, latency, tokens/usage when available, structured-output validation success/failure, expected-versus-observed outcome, observable quality/result, and fallback used when applicable; primary bonus evidence SHALL be a normal local run using both `qwen3.5:4b` and `qwen3.5:9b`, and cloud fallback SHALL NOT satisfy this evidence. | Multi-model comparison report linked to the local E2E trace and validation records. |
| FR-077 | An agent SHALL receive at most `MAX_LOCAL_RETRIES=1` local retry only for availability or transport failures: unavailable LLM, unavailable local model, agent timeout, or transient availability-attributable error; after a repeated eligible failure, the workflow may use cloud fallback only under FR-055. | Fault-injection traces distinguishing availability retries from quality repairs. |
| FR-078 | `README.md` SHALL document the purpose, architecture, technologies, installation, configuration, execution, environment variables, required Ollama models, optional cloud configuration, and demo commands. | README completeness review against the named topics. |
| FR-079 | The final documentation SHALL include an architecture diagram that conceptually shows User → LangGraph → Agents → RAG / MCP → External Systems → Langfuse. | Diagram review against the required conceptual flow. |
| FR-080 | The final documentation SHALL include a LangGraph diagram that shows nodes, normal edges, conditional edges, remediation loops, error routes, HITL, and termination. | Diagram review against the graph contract. |
| FR-081 | The final RAG documentation SHALL explain the corpus, loaders, chunking, chunk size, overlap, embeddings, Chroma, specialized retrieval, retrieval count, relevance, provenance, and `NO_RELEVANT_DOCS`. | RAG documentation completeness review. |
| FR-082 | The final MCP documentation SHALL explain MCP servers, tools, tool schemas, permissions, least privilege, the agents using each tool, error handling, and at least one example where `ToolResult` changes a LangGraph decision. | MCP documentation review and linked ToolResult decision evidence. |
| FR-083 | The final documentation SHALL provide verifiable Langfuse evidence for at least one complete execution. | Trace identifier, access evidence, and trace-completeness review. |
| FR-084 | The final evaluation report SHALL include the five scenarios, expected-versus-observed outcomes, scores, aggregate metrics, multi-model evaluation, and relevant errors/fallbacks. | Evaluation-report completeness review linked to scenario records. |
| FR-085 | The system SHALL provide a reproducible documented demo that exposes requirement entry; Product and ProductSpecification; Architecture; RAG retrieval and provenance; Developer; a Repository MCP call; Security; applicable Quality MCP or security evidence; Testing; test execution or testing evidence; Reviewer; APPROVED or REJECTED; a conditional remediation loop when applicable; a Langfuse trace; FinalReport; and models used. | Executed demo transcript, trace, and FinalReport using documented commands. |
| FR-086 | Final documentation SHALL describe each mandatory HITL route—Security severity `CRITICAL` and `MAX_ITERATIONS=3` without approval leading to `HUMAN_REVIEW_REQUIRED`—including where it occurs, trigger condition, reason for human intervention, mitigated risk, information received by the human, and how the workflow resumes or terminates. | HITL documentation completeness review and corresponding route evidence. |

## 5. Non-functional requirements

| ID | Requirement | Required evidence |
| --- | --- | --- |
| NFR-001 | The runtime SHALL support Python 3.10 or newer. | Runtime-version test. |
| NFR-002 | The user-facing execution interface SHALL be a CLI. | CLI acceptance test. |
| NFR-003 | The system SHALL remain a modular monolith with explicit module boundaries and no microservice dependency. | Architecture conformance review. |
| NFR-004 | LangChain SHALL have the bounded productive responsibility of representing and splitting RAG documents; it SHALL NOT orchestrate the workflow or replace Sentence Transformers, Chroma, or LangGraph. | Runtime RAG integration test proving use of official LangChain document and splitting components. |
| NFR-005 | LangGraph SHALL be the only workflow orchestrator. | Dependency and graph conformance test. |
| NFR-006 | Decision-affecting structured outputs SHALL use Pydantic validation. | Schema-validation coverage report. |
| NFR-007 | Local model inference SHALL use Ollama. | Provider evidence in a local E2E trace. |
| NFR-008 | RAG embeddings and vector storage SHALL use Sentence Transformers and Chroma, respectively. | Retrieval pipeline evidence. |
| NFR-009 | The core workflow SHALL remain operational without cloud providers or cloud credentials. | Offline/local-only E2E test. |
| NFR-010 | Approval, routing, iteration limits, and model selection SHALL be deterministic for the same validated state and configuration. | Repeatability tests over identical inputs. |
| NFR-011 | All repository operations SHALL remain inside the authorized workspace and SHALL reject path traversal or resolved paths outside it. | Sandbox and traversal security tests. |
| NFR-012 | Secrets SHALL be redacted from prompts, state snapshots, logs, traces, reports, test fixtures, and outbound requests. | Secret-seeding leakage test. |
| NFR-013 | Tool access SHALL be deny-by-default and limited by per-agent allowlists. | Permission-policy tests. |
| NFR-014 | LLM, RAG, MCP, and agent operations SHALL enforce externally configurable timeouts and SHALL report elapsed latency. | Timeout configuration and fault tests. |
| NFR-015 | Langfuse telemetry SHALL correlate every node, retrieval, tool call, model call, fallback, error, retry, HITL event, and final result with one root trace. | Trace-correlation test. |
| NFR-016 | Automated verification SHALL use pytest and SHALL make pass/fail evidence reproducible from the authorized workspace. | pytest execution report. |
| NFR-017 | Paid cloud usage SHALL be disabled by default. | Default-configuration assertion. |
| NFR-018 | Destructive repository operations SHALL require explicit authorization and SHALL never be inferred from an agent recommendation alone. | Denied destructive-operation tests and audit evidence. |

## 6. Acceptance criteria

| ID | Acceptance criterion |
| --- | --- |
| AC-001 | Given a valid CLI requirement, a run finishes with a unique `run_id`, a `FinalReport`, and a correlated Langfuse trace. |
| AC-002 | A successful trace shows the six core agents in the required order and no additional core agent. |
| AC-003 | Graph inspection proves multiple StateGraph nodes, normal edges, conditional edges, at least one loop, error paths, HITL, and terminal routes. |
| AC-004 | A completed state contains every field required by FR-006 and preserves its history through remediation. |
| AC-005 | Per-agent input inspection proves that unnecessary state fields are not supplied. |
| AC-006 | Every decision-affecting output has separate system/user prompt evidence and a successful Pydantic validation result. |
| AC-007 | `Reviewer=APPROVED` produces `final_status=APPROVED` and no later agent execution. |
| AC-008 | `Reviewer=REJECTED` with an allowed `return_to` executes that remediation route and returns to required validation. |
| AC-009 | A disallowed `return_to` is blocked, recorded, and never executed. |
| AC-010 | Three failed remediation cycles produce `HUMAN_REVIEW_REQUIRED`; a fourth cycle cannot start. |
| AC-011 | A `CRITICAL` Security finding pauses at HITL before approval, fallback, or automated remediation. |
| AC-012 | Product output includes all fields in FR-021 and each field maps to supplied input or an explicit assumption/ambiguity. |
| AC-013 | Architecture output includes all fields in FR-022 and every RAG-backed claim maps to retrieved provenance. |
| AC-014 | Developer evidence shows real workspace inspection and a concrete non-empty technical proposal reporting action mode, inspected/proposed files, diff or pseudodiff, repository evidence, validation strategy/result, and security-surface impact; empty output requires a specific no-op justification. |
| AC-015 | Security produces a result for every category in FR-028 and its structured outcome contains all fields in FR-029. |
| AC-016 | Testing covers all categories in FR-030 and distinguishes proposed, generated, executed, and actual results. |
| AC-017 | Reviewer scores every dimension in FR-032, emits every field in FR-033, and cannot bypass route validation. |
| AC-018 | The RAG inventory has at least five real documents and retrieval evidence contains every applicable provenance field in FR-037. |
| AC-019 | A no-match retrieval returns `NO_RELEVANT_DOCS`, records `RAG_ERROR`, and produces no invented source. |
| AC-020 | Real MCP server discovery exposes every operation in FR-041 and FR-042, a real client establishes a protocol session over stdio, and operations outside each agent allowlist remain denied. |
| AC-021 | A failed `run_tests` result transported through the real MCP protocol is preserved and produces TestResult FAIL, Reviewer REJECTED, and a remediation route. |
| AC-022 | One normal local E2E trace proves actual successful use of both `qwen3.5:4b` and `qwen3.5:9b` under the fixed agent mapping. |
| AC-023 | The local multi-model acceptance run passes without any cloud invocation; cloud is not counted as evidence for the multi-model bonus. |
| AC-024 | Cloud fault tests prove local-first ordering, allowed causes, fixed provider mappings, one escalation per agent, and three per run. |
| AC-025 | With all cloud keys absent, local execution remains available and records no secret or attempted paid call. |
| AC-026 | Langfuse exposes all items in FR-061 under a single root trace without leaking seeded secrets. |
| AC-027 | Fault-injection tests independently exercise every error behavior in FR-062 through FR-069. |
| AC-028 | Sandbox tests reject path traversal, outside-workspace access, unauthorized tools, and unauthorized destructive operations. |
| AC-029 | FinalReport validation fails when any field in FR-070 is absent and passes when all fields are present. |
| AC-030 | SC-01 passes only when observed status is APPROVED and evidence proves a 15-minute, single-use recovery link. |
| AC-031 | SC-02 passes only when observed status is APPROVED and evidence proves locking after exactly five failed attempts. |
| AC-032 | SC-03 passes only when observed status is APPROVED and evidence proves at most five transactions belonging to the authorized user. |
| AC-033 | SC-04 passes only when observed status is REJECTED and findings identify the non-expiring reset token risk. |
| AC-034 | SC-05 passes only when observed status is REJECTED and findings identify authorization failure and IDOR. |
| AC-035 | Each of the five scenario records contains every field in FR-072, all six scores in FR-073, and `pass=true` only when expected and observed outcomes match. |
| AC-036 | RAG documentation identifies and justifies every parameter in FR-074 without fixing unapproved concrete parameter values, and applicable parameters are evidenced as configurable. |
| AC-037 | A separate LIVE aggregate from five local-model runs contains every metric in FR-075, has LLM calls greater than zero and latency by agent/model, preserves three APPROVED and two REJECTED outcomes, and marks unavailable provider metrics as unavailable rather than assigning values. |
| AC-038 | Multi-model evaluation compares all fields in FR-076 and proves its primary evidence through one normal local run that actually uses both `qwen3.5:4b` and `qwen3.5:9b`; cloud fallback is excluded from satisfying the bonus. |
| AC-039 | Fault-injection evidence proves that availability failures consume at most one `MAX_LOCAL_RETRIES` retry, response-quality failures consume at most one `MAX_LOCAL_REPAIRS` repair, and each follows its distinct eligible fallback path. |
| AC-040 | README, both required diagrams, RAG documentation, MCP documentation, verifiable complete Langfuse evidence, and the evaluation report exist and satisfy FR-078 through FR-084. |
| AC-041 | A documented command sequence reproduces the demo and exposes every required observation in FR-085. |
| AC-042 | HITL documentation covers only the two mandatory routes, includes every explanation required by FR-086, and aligns with the corresponding graph routes. |

## 7. Evaluation scenarios

Exactly these five scenarios form the minimum acceptance evaluation set.

| Scenario | Requirement input | Expected status | Expected security signal |
| --- | --- | --- | --- |
| SC-01 Password Recovery | Provide a password-recovery link that expires after 15 minutes and can be used only once. | APPROVED | Enforced 15-minute expiration and single-use invalidation. |
| SC-02 Account Locking | Lock an account after five failed authentication attempts. | APPROVED | Lockout occurs after exactly five failures. |
| SC-03 Transaction History API | Return only the latest five transactions belonging to the authorized user. | APPROVED | Ownership authorization and maximum result count of five. |
| SC-04 Non-expiring password reset token | Provide a password-reset token that never expires. | REJECTED | Unsafe token lifetime is identified. |
| SC-05 Transactions by arbitrary ID | Allow access to any user's transactions using only that user's ID. | REJECTED | Authorization failure and IDOR are identified. |

For every scenario, the evaluation record shall contain:
`expected_status`, `observed_status`, `status_match`,
`expected_security_signal`, `observed_findings`, `reviewer_score`,
`iterations`, `models_used`, `rag_sources`, `tools_used`, `trace_id`, and
`pass`.

## 8. Evaluation dimensions

Each scenario and the aggregate evaluation shall report:

1. Requirements completeness.
2. Architecture correctness.
3. Security compliance.
4. Testing completeness.
5. Implementation consistency.
6. RAG grounding.

The Reviewer may issue `APPROVED` only when required evidence is present and
the deterministic acceptance checks for the applicable scenario pass.

## 9. Final report contract

The user-visible `FinalReport` shall contain exactly these named sections:

1. FEATURE
2. STATUS
3. REQUIREMENTS
4. ARCHITECTURE
5. SECURITY
6. TESTING
7. IMPLEMENTATION
8. RISK
9. ITERATIONS
10. DOCUMENTATION USED
11. TOOLS EXECUTED
12. MODELS USED
13. ERRORS / DEGRADATIONS
14. TRACE ID
15. NEXT ACTION

## 10. Traceability and evidence policy

- Every FR and NFR has a required-evidence entry in Sections 4 and 5.
- Evidence shall reference the same `run_id` or trace correlation identifier
  as the run it supports.
- Derived summaries shall not replace raw validation, retrieval, MCP, test,
  model-usage, or routing evidence.
- Missing required evidence shall prevent deterministic approval.

## 11. Out of scope

The following are not requirements for this feature and shall not be treated
as implied bonus work:

- Parallel Agents.
- Memory.
- Auto-PR.
- n8n.
- Qdrant.
- Complex UI.

The only required MVP+ bonus is deterministic, observable local Multi-model
execution. Cloud fallback is a contingency and does not satisfy that bonus.

## 12. Blocking ambiguities

None. The requirements, policies, expected outcomes, evidence contracts, and
error behaviors needed to proceed to Plan are defined in this specification.
