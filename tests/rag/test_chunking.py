from collections import Counter

from langchain_core.documents import Document

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


def test_each_knowledge_source_is_substantive_and_sectioned() -> None:
    documents = load_documents("knowledge")
    sections = Counter(item.metadata["source"] for item in documents)
    words = Counter()
    for document in documents:
        words[document.metadata["source"]] += len(document.page_content.split())

    assert set(sections) == {
        "api-design-guidelines.md", "architecture-guidelines.md",
        "coding-standards.md", "owasp-api-security.md",
        "security-guidelines.md", "testing-strategy.md",
    }
    assert all(count >= 4 for count in sections.values())
    assert all(count >= 120 for count in words.values())


def test_markdown_loader_preserves_sections(tmp_path) -> None:
    source = tmp_path / "security-guidelines.md"
    source.write_text("# Security\n\n## Authorization\n\nPrevent IDOR with ownership checks.", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert isinstance(documents[0], Document)
    assert documents[0].metadata["domain"] == "security"
    assert documents[0].metadata["section"] == "Security / Authorization"


def test_rag_ingestion_uses_langchain_document_and_text_splitter(tmp_path) -> None:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    from engineering_team.rag.loaders import build_text_splitter, chunk_documents

    source = tmp_path / "architecture-guidelines.md"
    source.write_text("# Boundaries\n\n" + "bounded context " * 300, encoding="utf-8")
    documents = load_documents(tmp_path)
    splitter = build_text_splitter(chunk_size=80, overlap=16)
    chunks = chunk_documents(documents, chunk_size=80, overlap=16)

    assert all(isinstance(item, Document) for item in documents)
    assert isinstance(splitter, RecursiveCharacterTextSplitter)
    assert len(chunks) > 1
    assert all(item.source == source.name for item in chunks)
    assert all(item.section == "Boundaries" for item in chunks)
