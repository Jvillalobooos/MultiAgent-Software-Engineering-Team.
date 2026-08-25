from pathlib import Path


def test_required_documentation_and_demo_commands_are_present() -> None:
    required = [
        "README.md", "docs/architecture/overview.md", "docs/diagrams/architecture.md",
        "docs/diagrams/langgraph.md", "docs/rag.md", "docs/mcp.md",
        "docs/evaluation.md", "docs/demo-runbook.md",
        "docs/evidence/final-audit.md",
    ]
    for filename in required:
        assert Path(filename).is_file(), filename

    combined = "\n".join(Path(filename).read_text(encoding="utf-8") for filename in required)
    for phrase in (
        "Sentence Transformers", "Chroma", "NO_RELEVANT_DOCS", "run_tests",
        "HUMAN_REVIEW_REQUIRED", "qwen3.5:4b", "qwen3.5:9b", "LANGFUSE_PUBLIC_KEY",
        "SC-01", "SC-05", "scripts/run_evaluation.py", "scripts/run_multimodel.py",
        "LangChain Document", "MCP Server", "stdio", "--live-models",
        "scenarios-live.json",
    ):
        assert phrase in combined
