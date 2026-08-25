# Final compliance audit evidence

This evidence is sanitized: it contains identifiers and reproducible commands,
not credentials, prompts, responses, or secret values.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest tests/mcp/test_protocol.py -q
.\.venv\Scripts\python.exe -m pytest tests/rag -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_developer_agent.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_workflow.py -k real_mcp_protocol -q
.\.venv\Scripts\python.exe -m scripts.run_evaluation --live-models
$env:CLOUD_ENABLED='false'; .\.venv\Scripts\python.exe -m scripts.run_multimodel
.\.venv\Scripts\python.exe -m ruff check src tests evaluation sample_app scripts
.\.venv\Scripts\python.exe -m pytest
```

## Real MCP protocol

The workflow used `MCPRepositoryClient` and `MCPQualityClient` over official
MCP stdio sessions. Negotiated protocol metadata was `2026-07-28`; servers
identified independent Repository and Quality surfaces. ToolResults preserved
`mcp://repository/...` and `mcp://quality/...` evidence. The focused integration
test demonstrates `run_tests FAIL → TestResult FAIL → Reviewer REJECTED →
Developer/Testing remediation → Reviewer` through the real server process.
Protocol tests also verify persistent stateful getters, real create/update
diffs, and synthetic `.env`/`.env.*` search exclusion without using secrets.

## LangChain and RAG

The real ingestion path is `LangChain Document → LangChain
RecursiveCharacterTextSplitter → Sentence Transformers → persistent Chroma →
specialized retriever → RetrievedEvidence`. Focused tests preserve metadata and
provenance, real match, `NO_RELEVANT_DOCS`, and Chroma reopen persistence.

## Five-scenario LIVE local evaluation

Evidence files: `evaluation/reports/scenarios-live.json` and
`evaluation/reports/aggregate-live.json`.

| Scenario | Run ID | Trace ID | Observed | Iterations | LLM calls |
| --- | --- | --- | --- | ---: | ---: |
| SC-01 | `sc-01-5fd3f10e-2dcf-4daf-ac3a-83b555120d4f` | `9e49cbf9039fd06d2285a051ba2ac563` | APPROVED | 0 | 6 |
| SC-02 | `sc-02-66fbee34-ec7b-41f7-a998-3ff9ad7f11ef` | `b47a7f60f5d63ee00b2d22b5a7355574` | APPROVED | 0 | 6 |
| SC-03 | `sc-03-383925e7-123a-4fa0-8f49-4cea2c80c106` | `40b48572da7bf0f8de64fb73c29659bd` | APPROVED | 0 | 6 |
| SC-04 | `sc-04-803562b0-2750-4003-bbc6-66f257a961c1` | `559e46dca7e0b8aff62fe47682b817e1` | REJECTED | 3 | 14 |
| SC-05 | `sc-05-c3b11410-6e7c-4e32-a318-5f34bcb41605` | `edb28b450fee1774ade9c66da5baf468` | REJECTED | 3 | 14 |

All five records have `status_match=true`, `pass=true`, live Langfuse export,
real MCP evidence, and only provider `ollama`. Aggregate evidence records 9.2
average LLM calls, measured latency for both local models, 3 APPROVED, 2
REJECTED, zero cloud fallback, and no structured-output failure.

SC-04 and SC-05 preserve Reviewer REJECTED as the evaluation outcome; their
third rejected cycle deterministically reaches HITL with no fourth cycle.

## Multi-model and Langfuse LIVE

Normal local run `multimodel-afe1bfc1-4eb5-45ef-a0e3-012ba6a9469c`, trace
`971713e4db8ae084c18abdad2b1fdd99`, is APPROVED with bonus pass. It contains
six successful Ollama invocations across `qwen3.5:4b` and `qwen3.5:9b`, no
cloud use, real MCP tool calls, and `langfuse_live=true` after adapter flush.

The five scenario trace IDs above also exported LIVE root observations with
Product, Architecture/RAG, Developer/MCP, Security/RAG/MCP, Testing/MCP,
Reviewer, routing/HITL when applicable, and FinalReport.

## Final static and test gates

- Pytest: `115 passed, 1 external dependency warning`; zero failures.
- Ruff: `All checks passed!` for `src tests evaluation sample_app scripts`.
