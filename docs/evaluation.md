# Evaluation, observability, and HITL

## Five fixed scenarios

| ID | Scenario | Expected | Observed | Pass signal |
|---|---|---:|---:|---|
| SC-01 | Password Recovery | APPROVED | APPROVED | 15 minutes and single-use |
| SC-02 | Account Locking | APPROVED | APPROVED | lock after exactly 5 attempts |
| SC-03 | Transaction History API | APPROVED | APPROVED | authorized owner, maximum 5 |
| SC-04 | Non-expiring reset token | REJECTED | REJECTED | unsafe lifetime detected |
| SC-05 | Arbitrary user transactions by ID | REJECTED | REJECTED | authorization failure / IDOR |

For SC-04 and SC-05, matching `REJECTED` is evaluation PASS. The harness does
not alter expected statuses. Every JSON record includes expected/observed,
status_match, expected security signal, observed findings, reviewer score and
six subscores, iterations, models, RAG sources, tools, trace_id and `pass`.
`pass` also requires the scenario-specific executable acceptance check. SC-01
inspects the persisted expiry and consumes the token twice; SC-02 checks every
transition through attempt 5; SC-03 executes both the five-item limit and
cross-user denial. SC-04/05 require the expected security signal and verify
that the secure sample application does not implement the unsafe behavior.
This evidence is stored in `acceptance_evidence` and enters the workflow as a
`scenario_acceptance` ToolResult.
Each scenario first creates `workspace/evaluation/<run_id>` from the sample
application. The service module, Repository MCP, Quality MCP, scanners and
pytest all operate on that run copy.

Run `python scripts/run_evaluation.py` to write
`evaluation/reports/scenarios.json` and `aggregate.json`. Aggregate values are
derived from records: duration, LLM/tool/retrieval calls, iterations, exposed
token usage, outcomes, latency by agent/model, fallback rate, structured
output validation and errors. Missing usage is `unavailable`, never estimated.

Run `python scripts/run_evaluation.py --live-models` for the separate LIVE
acceptance. It invokes LocalModelRuntime and ModelRouter for all five scenarios,
uses real Repository/Quality MCP stdio sessions, exports each root trace through
the project Langfuse adapter, and writes `scenarios-live.json` plus
`aggregate-live.json`. LIVE acceptance requires non-zero LLM calls, measured
latency by agent/model, both qwen3.5 tags, no cloud substitution, three
APPROVED outcomes and two REJECTED outcomes.

Run `python scripts/run_multimodel.py` for the normal real Ollama proof. Its
record contains requested/actual model, agent, provider, profile, latency,
usage when Ollama supplies it, structured_output_success, fallback_used and
error. Bonus PASS requires all six roles, both `qwen3.5:4b` and `qwen3.5:9b`
in the same run, ModelRouter selection, and no cloud substitution.

The sentence-transformers bootstrap may print an unauthenticated Hugging Face
Hub warning. It is not a workflow or Langfuse error: local downloads continue
with lower Hub rate limits. `HF_TOKEN` is optional and only needed for higher
download limits or private Hub assets.
For a fully cached verification, set `HF_HUB_OFFLINE=1`; this suppresses Hub
access without changing model routing, capability detection, or acceptance
gates.

## Langfuse

One root trace is seeded by `run_id`. Child observations cover Product,
Architecture, Developer, Security, Testing, Reviewer, requested/actual model,
provider/profile/latency/usage, separate prompts and responses, RAG retrieval,
MCP calls and ToolResult, retry, repair, fallback, errors, iterations, HITL and
FinalReport. Payloads pass recursive secret redaction.

Live export uses `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
`LANGFUSE_BASE_URL`. `LANGFUSE_HOST` is accepted only as a lower-priority
legacy alias. Without keys the same adapter records correlated local events;
only LIVE Langfuse evidence remains `BLOCKED_CREDENTIAL`, never the core.
Every run also writes its redacted event sequence to
`evaluation/reports/traces/<run_id>.json`, including routes and FinalReport.
If the configured Langfuse endpoint rejects or loses its HTTP connection during
the initial authentication check, the adapter records `LANGFUSE_UNAVAILABLE`
and uses that same local trace path. Observability unavailability does not abort
Product or any later workflow stage.
Set `LANGFUSE_OFFLINE=true` to force the correlated local trace even when keys
remain configured. This is the reproducible option for offline acceptance runs
because it prevents the asynchronous exporter from starting; it does not alter
agent routing, validation, delivery gates, or the redacted trace artifact.

Model JSON is schema-validated and then checked against deterministic governed
facts. A schema-valid response may elaborate non-routing content, but cannot
weaken security status/severity/checklist, test status/failures, Reviewer
status/return route, or remove required evidence. Contradictions consume the
single repair allowance and then follow quality-error fallback/HITL policy.
The exact/additive/enrichable/mutation classifications come from one central
registry used by all six roles, so prompt wording and semantic enforcement
cannot drift independently.

Every run traces the `ProjectCapabilities` decision, sanitized ecosystem/root,
profile fingerprint, native argv execution and terminal capability errors.
Unknown, ambiguous, or missing-test projects produce
`PROJECT_CAPABILITY_ERROR` and `INCOMPLETE` before model work. Python,
Node/TypeScript, .NET, Java, Go and Rust use their own declared test patterns;
Quality independently re-detects the profile before every command.

Developer receives at most two inspected source files, and each file is
included up to the same 4,000-character boundary used to decide whether the
agent may safely produce a complete-file mutation. Its generation budget is
4,096 tokens so the two-file mutation contract is not truncated at the former
1,400-token boundary. Because Ollama's `/api/generate` calls are stateless, an
invalid structured response is embedded as untrusted data in the one permitted
repair request; the model is not asked to repair context that it cannot see.
Reviewer receives 1,200 output tokens so its complete decision, subscores,
problems and evidence references are not truncated at the former 500-token
boundary.

Developer and Testing receive the actual governed business rules, constraints,
and acceptance criteria in bounded context. Testing mutation paths must be
unique after slash/case normalization, at most one test mutation is accepted
per invocation, and each accepted test file must exercise a behavior identifier
from the inspected implementation contract. Behavioral setup comes from an
existing API/helper/fixture or deterministic implementation evidence, never an
opaque inconsistent value. A duplicate overwrite or unrelated pre-existing
test is rejected before any write and cannot satisfy the generated-test gate.

After a downstream rejection, inspect `remediation_request` separately from
the Reviewer audit reason. The request must include the latest relevant failed
Quality `ToolResult` or Security scanner result, its status, a bounded causal
output summary, and evidence reference. Developer also receives the prior
`ImplementationResult`/diff, but the visible evidence does not expand its tool
allowlist. This distinction proves that causal context propagated without
granting test or scanner execution authority.

Security evaluation is monotonic. A baseline scanner `PASS` may become model
`FAIL` only with grounded findings from the bounded implementation/diff,
scanner output, and RAG fragments. A deterministic `FAIL`, severity, failed
checklist control, or HITL requirement can never be weakened. RAG prompt
evidence must show bounded fragment content and source/section/chunk/score
provenance, rather than identifiers alone.

Langfuse retains every quality attempt. An invalid attempt is recorded as
`WARNING` while its local repair remains available, with
`structured_output_success=false` and `LLM_QUALITY_ERROR` preserved in event
metadata. A successful repair is a subsequent `DEFAULT` generation. If the
repair is exhausted, the final failed attempt is `ERROR` and the graph records
the terminal quality-error/fallback route. Offline repair exhaustion ends as
`HUMAN_REVIEW_REQUIRED` with `LLM_QUALITY_ERROR`, not opaque `INCOMPLETE`.
This keeps recovered runs visible
without presenting a corrected transient attempt as an unrecovered Langfuse
error.

## Interactive HITL route and autonomous outcomes

### Security CRITICAL

Location: conditional edge immediately after Security when the graph is built
with `interactive_hitl=True`. Trigger: highest severity `CRITICAL`, regardless
of later evidence or cloud. The human receives the sanitized requirement,
validated finding, provenance, bounded diff/tool evidence and trace
correlation. `RESUME` follows only the predefined validation path; `TERMINATE`
leaves `HUMAN_REVIEW_REQUIRED`. The interactive graph uses a LangGraph
checkpointer and `interrupt`; a later `Command(resume=...)` resumes the same
`thread_id`. A normal non-interactive run records the same evidence and ends as
`INCOMPLETE` instead of pausing.

### MAX_ITERATIONS=3

Location: Reviewer conditional route. Trigger: the third rejected remediation
cycle, an invalid remediation route, or another unrecoverable non-interactive
workflow error. The run terminates as `INCOMPLETE`, preserving all decisions,
iteration history, latest validated stage summaries, tool/RAG evidence and
safe errors in its final report. No fourth automated cycle exists.

## Run decision documents

For a normal run, `sample_app` is the default target unless `--project` names
another directory. Product writes `docs/decisions/product-specification.md` and
Architecture writes `docs/decisions/architecture-decisions.md` inside the
isolated run workspace. Developer writes only through Repository MCP and only
after inspecting a safe workspace path. `APPROVED` means the changes were
applied and validated; `INCOMPLETE` means the report contains diagnostics for a
new attempt.
