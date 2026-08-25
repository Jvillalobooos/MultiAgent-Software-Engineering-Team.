# Real MCP Servers, client, and routing effect

The production boundary is:

`LangGraph → MCP Client adapter → official MCP protocol over stdio → MCP Server → bounded backend → isolated workspace/tools`.

`engineering_team.mcp.server` uses the official Python MCP SDK and starts
independent Repository or Quality tool surfaces. `engineering_team.mcp.client`
opens a lifecycle-managed negotiated stdio session, discovers tools, performs
related calls on that same session, then closes the process explicitly. It
converts structured results back to Pydantic `ToolResult`.
The existing Python classes are bounded server backends; direct calls are not
the primary protocol evidence.

Repository MCP exposes `list_files`, `read_file`, `search_code`,
`get_file_content`, `create_file`, `update_file` and `get_diff`. Architecture
has read-only access; Developer has bounded read/write access inside the
per-run copy. Resolved external paths and `..` traversal are denied.
Symlinks and `.env`/`.env.*` are excluded consistently from listing and search
so secret paths and links cannot escape or leak from the run copy. Read calls
apply the same resolved-path and secret policy. `get_diff` compares writes to
their captured original content and returns a real unified diff.

Quality MCP exposes `run_tests`, `get_test_results`, `run_build`,
`get_build_status`, `run_linter`, `scan_dependencies`, `run_security_scan` and
`get_security_report`. Testing owns test execution; Developer receives only
build/lint; Security receives only dependency/security scans. Calls validate
role, arguments, timeout and status and return a Pydantic `ToolResult` with
safe input/output summaries, duration, evidence reference and normalized
error. Access is deny-by-default. The persistent session makes `run_tests →
get_test_results`, `run_build → get_build_status`, and `run_security_scan →
get_security_report` preserve backend results across protocol calls.
Timeout is adapter-configurable. In the real multi-model run, Repository and
Quality MCP both execute against the isolated run copy; its copied
`test_acceptance.py` is the test target.

MCP is not ornamental. The real-protocol integration test executes:

`run_tests FAILED → ToolResult FAIL → TestResult FAIL → Reviewer REJECTED → Developer → Testing → Reviewer`.

The failed ToolResult remains in `EngineeringState.tool_results`; the second
test execution can approve after remediation. `MCP_ERROR` and `TOOL_ERROR`
remain dedicated graph errors and never activate cloud automatically.

```powershell
.\.venv\Scripts\python.exe -m pytest tests/mcp/test_protocol.py -q
.\.venv\Scripts\python.exe -m pytest tests/integration/test_workflow.py -k real_mcp_protocol -q
```

Every protocol result carries an `mcp://repository/...` or `mcp://quality/...`
evidence reference. `.env`, traversal, external resolutions and symlinks are
not readable; role allowlists remain deny-by-default.
