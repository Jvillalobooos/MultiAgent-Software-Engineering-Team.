"""Composition helpers for the approved local RAG pipeline."""

from pathlib import Path

from engineering_team.config import Settings

from .index import ChromaIndex
from .loaders import chunk_documents, load_documents
from .retrievers import SpecializedRetriever


def build_retriever(
    settings: Settings,
    persist_directory: str | Path | None = None,
    *,
    knowledge_directory: str | Path = "knowledge",
    reindex: bool = False,
) -> SpecializedRetriever:
    index = ChromaIndex(persist_directory or settings.rag_persist_directory)
    if reindex or index.count == 0:
        documents = load_documents(knowledge_directory)
        chunks = chunk_documents(
            documents,
            chunk_size=settings.rag_chunk_size,
            overlap=settings.rag_chunk_overlap,
        )
        index.replace(chunks)
    return SpecializedRetriever(
        index,
        top_k=settings.rag_top_k,
        fetch_k=settings.rag_fetch_k,
        min_relevance=settings.rag_min_relevance,
    )


__all__ = ["ChromaIndex", "SpecializedRetriever", "build_retriever"]
