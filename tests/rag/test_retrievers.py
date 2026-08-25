from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.state import EngineeringState
from engineering_team.models.context import build_context
from engineering_team.rag.index import ChromaIndex
from engineering_team.rag.loaders import DocumentChunk, chunk_documents, load_documents
from engineering_team.rag.retrievers import SpecializedRetriever


def test_specialized_retriever_returns_provenance() -> None:
    chunk = DocumentChunk(
        source="security.md",
        domain="security",
        section="Authorization",
        version="local",
        chunk_id="security.md:0",
        text="authorization IDOR access control",
    )
    retriever = SpecializedRetriever.from_chunks([chunk], min_relevance=0.0)
    evidence = retriever.retrieve("authorization", agent=AgentRole.SECURITY)

    assert evidence[0].source == "security.md"
    assert evidence[0].chunk_id == "security.md:0"


def test_specialized_retriever_returns_no_relevant_docs() -> None:
    retriever = SpecializedRetriever.from_chunks([], min_relevance=0.55)
    assert retriever.retrieve("anything", agent=AgentRole.SECURITY) == []
    assert retriever.last_status == "NO_RELEVANT_DOCS"
    assert retriever.last_error is not None
    assert retriever.last_error.code is ErrorCode.RAG_ERROR


def test_real_sentence_transformers_chroma_match_and_persistence(tmp_path) -> None:
    chunks = chunk_documents(load_documents("knowledge"), chunk_size=800, overlap=160)
    index_path = tmp_path / "chroma"
    index = ChromaIndex(index_path, collection_name="acceptance-rag")
    index.replace(chunks)

    retriever = SpecializedRetriever(index, top_k=4, fetch_k=8, min_relevance=0.55)
    evidence = retriever.retrieve(
        "How should an API prevent IDOR authorization failures with ownership checks?",
        agent=AgentRole.SECURITY,
    )

    assert evidence
    assert all(item.source and item.section and item.chunk_id and item.fragment for item in evidence)
    assert all(item.domain in {"security", "owasp"} for item in evidence)
    assert retriever.pipeline == [
        "source documents", "LangChain Document", "LangChain text splitting",
        "Sentence Transformers", "embeddings", "Chroma", "specialized retriever",
        "RetrievedEvidence", "agent",
    ]

    reopened = ChromaIndex(index_path, collection_name="acceptance-rag")
    assert reopened.count == len(chunks)
    assert SpecializedRetriever(reopened).retrieve(
        "single-use password reset token expiration", agent=AgentRole.SECURITY
    )


def test_real_chroma_no_match_does_not_invent_sources(tmp_path) -> None:
    index = ChromaIndex(tmp_path / "chroma", collection_name="no-match")
    index.replace(chunk_documents(load_documents("knowledge"), chunk_size=800, overlap=160))
    retriever = SpecializedRetriever(index, min_relevance=0.99)

    evidence = retriever.retrieve(
        "zygomorphic quasar botany unrelated phrase", agent=AgentRole.ARCHITECTURE
    )

    assert evidence == []
    assert retriever.last_status == "NO_RELEVANT_DOCS"
    assert retriever.last_sources == []


def test_context_isolates_rag_by_agent_domain() -> None:
    architecture = DocumentChunk(
        source="architecture.md", domain="architecture", section="Boundaries",
        version="local", chunk_id="a:0", text="modular boundaries",
    ).to_evidence("boundaries", 0.9)
    security = DocumentChunk(
        source="security.md", domain="security", section="Authorization",
        version="local", chunk_id="s:0", text="ownership authorization",
    ).to_evidence("authorization", 0.9)
    state = EngineeringState(
        run_id="run", requirement="requirement", rag_evidence=[architecture, security]
    )

    arch_context = build_context(AgentRole.ARCHITECTURE, state, "Architecture")
    security_context = build_context(AgentRole.SECURITY, state, "Security")

    assert [item.chunk_id for item in arch_context.rag_evidence] == ["a:0"]
    assert [item.chunk_id for item in security_context.rag_evidence] == ["s:0"]


def test_real_corpus_retrieval_is_differentiated_by_role_and_section(tmp_path) -> None:
    index = ChromaIndex(tmp_path / "chroma", collection_name="domain-quality")
    index.replace(chunk_documents(load_documents("knowledge"), chunk_size=800, overlap=160))
    retriever = SpecializedRetriever(index, top_k=4, fetch_k=8, min_relevance=0.55)

    architecture = retriever.retrieve(
        "module boundaries dependencies data changes and architecture risks",
        agent=AgentRole.ARCHITECTURE,
    )
    security = retriever.retrieve(
        "prevent IDOR with ownership authorization and safe secret handling",
        agent=AgentRole.SECURITY,
    )
    testing = retriever.retrieve(
        "test happy path errors edge cases security and business rules",
        agent=AgentRole.TESTING,
    )

    assert any(item.source == "architecture-guidelines.md" for item in architecture)
    assert any(item.source == "owasp-api-security.md" for item in security)
    assert any(item.source == "testing-strategy.md" for item in testing)
    for evidence in (architecture, security, testing):
        assert evidence
        assert all(item.section and item.chunk_id and item.fragment for item in evidence)
