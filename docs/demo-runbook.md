# Reproducible demo runbook

All commands run from the repository root in PowerShell.

## 1. Environment and model smoke

```powershell
.\.venv\Scripts\python.exe --version
ollama list
ollama run qwen3.5:4b "Reply exactly MODEL_OK"
ollama run qwen3.5:9b "Reply exactly MODEL_OK"
```

Expected model tags are `qwen3.5:4b` and `qwen3.5:9b`. Do not pull them again
when already present.

## 2. Focused gates

```powershell
$env:HF_HUB_OFFLINE='1'
$env:TRANSFORMERS_OFFLINE='1'
.\.venv\Scripts\python.exe -m pytest tests/rag -q
.\.venv\Scripts\python.exe -m pytest tests/mcp/test_protocol.py -q
.\.venv\Scripts\python.exe -m pytest tests/graph tests/mcp tests/integration -q
```

Observe a real Chroma match, `NO_RELEVANT_DOCS`, persistent collection,
remediation chains, CRITICAL HITL, iteration 3 stop and the failed `run_tests`
route.

## 3. Exact five scenarios

```powershell
.\.venv\Scripts\python.exe scripts/run_evaluation.py
Get-Content evaluation/reports/scenarios.json
Get-Content evaluation/reports/aggregate.json
```

Observe SC-01..SC-03 APPROVED and SC-04..SC-05 REJECTED with `pass: true`,
RAG provenance, Quality MCP tools, Reviewer scores and trace IDs.

```powershell
.\.venv\Scripts\python.exe scripts/run_evaluation.py --live-models
Get-Content evaluation/reports/scenarios-live.json
Get-Content evaluation/reports/aggregate-live.json
```

The LIVE files must show `llm_calls > 0`, latency for qwen3.5:4b/9b,
`langfuse_live: true`, and `mcp://` tool evidence. This is the primary local
five-scenario and multi-model evidence; the fast mode remains for regression.

## 4. Normal real multi-model run

```powershell
.\.venv\Scripts\python.exe scripts/run_multimodel.py
Get-Content evaluation/reports/multimodel-live.json
```

Observe requirement → Product/ProductSpecification → Architecture → real RAG
→ Developer → Repository MCP → Security → Quality MCP → Testing → Reviewer →
FinalReport. The same trace must show 4B for Architecture/Testing and 9B for
Product/Developer/Security/Reviewer, provider `ollama`, successful structured
output and no fallback. Remediation is demonstrated separately by the graph
and MCP E2E tests because this acceptance run is the normal APPROVED path.
Each response is the complete role-specific Pydantic artifact actually stored
by the graph. Inspect `trace_events` and
`evaluation/reports/traces/<run_id>.json` for redacted prompts, structured
responses, routes, MCP/RAG observations and FinalReport.
The post-model semantic guard rejects any schema-valid response that weakens
deterministic security, routing, failure, or provenance facts.

## 5. Langfuse and final gate

When Langfuse variables are configured, open the trace ID emitted by the run
and verify root/child completeness. Never print credential values.

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests evaluation sample_app scripts
.\.venv\Scripts\python.exe -m pytest
```

Absent Langfuse or cloud credentials are reported as credential status only;
local execution remains valid. Sanitized evidence records that Gemini and
Groq fallback were demonstrated LIVE previously. Routine regression uses
provider-shaped responses and does not repeat paid cloud calls; retry, repair,
provider mapping, budgets and graph-integrated fallback/HITL remain tested.
