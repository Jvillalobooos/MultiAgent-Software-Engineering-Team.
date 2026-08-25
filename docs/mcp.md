# MCP adapters and routing effect

Repository MCP exposes `list_files`, `read_file`, `search_code`,
`get_file_content`, `create_file`, `update_file` and `get_diff`. Architecture
has read-only access; Developer has bounded read/write access inside the
per-run copy. Resolved external paths and `..` traversal are denied.
Symlinks are excluded from repository search so links cannot escape the run
copy after traversal validation.

Quality MCP exposes `run_tests`, `get_test_results`, `run_build`,
`get_build_status`, `run_linter`, `scan_dependencies`, `run_security_scan` and
`get_security_report`. Testing owns test execution; Developer receives only
build/lint; Security receives only dependency/security scans. Calls validate
role, arguments, timeout and status and return a Pydantic `ToolResult` with
safe input/output summaries, duration, evidence reference and normalized
error. Access is deny-by-default.
Timeout is adapter-configurable. In the real multi-model run, Repository and
Quality MCP both execute against the isolated run copy; its copied
`test_acceptance.py` is the test target.

MCP is not ornamental. The integration test executes:

`run_tests FAILED → ToolResult FAIL → TestResult FAIL → Reviewer REJECTED → Developer → Testing → Reviewer`.

The failed ToolResult remains in `EngineeringState.tool_results`; the second
test execution can approve after remediation. `MCP_ERROR` and `TOOL_ERROR`
remain dedicated graph errors and never activate cloud automatically.
