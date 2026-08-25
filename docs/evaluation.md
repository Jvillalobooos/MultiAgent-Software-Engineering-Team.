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

Model JSON is schema-validated and then checked against deterministic governed
facts. A schema-valid response may elaborate non-routing content, but cannot
weaken security status/severity/checklist, test status/failures, Reviewer
status/return route, or remove required evidence. Contradictions consume the
single repair allowance and then follow quality-error fallback/HITL policy.

## Mandatory HITL routes

### Security CRITICAL

Location: conditional edge immediately after Security. Trigger: highest
severity `CRITICAL`, regardless of later evidence or cloud. Human intervention
prevents automated approval of potentially catastrophic exposure. The human
receives the sanitized requirement, validated finding, provenance, bounded
diff/tool evidence and trace correlation. `RESUME` follows only the predefined
validation path; `TERMINATE` leaves `HUMAN_REVIEW_REQUIRED`.
The interactive graph uses a LangGraph checkpointer and `interrupt`; a later
`Command(resume=...)` resumes the same `thread_id`.

### MAX_ITERATIONS=3

Location: Reviewer conditional route. Trigger: the third rejected remediation
cycle. Human intervention prevents an unbounded or self-approving loop. The
human receives all three decisions, iteration history, latest validated stage
summaries, tool/RAG evidence and safe errors. No fourth automated cycle exists;
the same explicit `RESUME` or `TERMINATE` decision contract applies.
