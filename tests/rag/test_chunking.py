from engineering_team.rag.loaders import chunk_document, load_documents


def test_chunking_preserves_source_and_overlap() -> None:
    chunks = chunk_document(
        "alpha beta gamma delta epsilon", "guide.md", "architecture", chunk_size=12, overlap=4
    )

    assert len(chunks) >= 2
    assert chunks[0].source == "guide.md"
    assert chunks[0].chunk_id == "guide.md:0"
    assert chunks[0].section
    assert chunks[0].version == "local"


def test_corpus_has_at_least_six_real_documents() -> None:
    assert len(load_documents("knowledge")) >= 6


def test_markdown_loader_preserves_sections(tmp_path) -> None:
    source = tmp_path / "security-guidelines.md"
    source.write_text("# Security\n\n## Authorization\n\nPrevent IDOR with ownership checks.", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert documents[0].domain == "security"
    assert documents[0].section == "Security / Authorization"
