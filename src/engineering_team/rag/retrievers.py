"""Specialized retrieval over the persistent semantic index."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import ClassVar

import numpy as np

from engineering_team.contracts.enums import AgentRole, ErrorCode
from engineering_team.contracts.models import RetrievedEvidence, WorkflowError

from .index import ChromaIndex, IndexedCandidate
from .loaders import DocumentChunk

_DOMAINS: dict[AgentRole, set[str]] = {
    AgentRole.ARCHITECTURE: {"architecture", "api"},
    AgentRole.DEVELOPER: {"coding"},
    AgentRole.SECURITY: {"security", "owasp"},
    AgentRole.TESTING: {"testing", "coding"},
}


class SpecializedRetriever:
    """Apply agent domain filters, MMR, relevance, and provenance conversion."""

    pipeline: ClassVar[list[str]] = [
        "source documents",
        "LangChain Document",
        "LangChain text splitting",
        "Sentence Transformers",
        "embeddings",
        "Chroma",
        "specialized retriever",
        "RetrievedEvidence",
        "agent",
    ]

    def __init__(
        self,
        index: ChromaIndex,
        top_k: int = 4,
        fetch_k: int = 8,
        min_relevance: float = 0.55,
    ) -> None:
        self._index = index
        self._top_k = top_k
        self._fetch_k = fetch_k
        self._min_relevance = min_relevance
        self.last_status = "OK"
        self.last_error: WorkflowError | None = None
        self.last_sources: list[str] = []

    @classmethod
    def from_chunks(
        cls, chunks: list[DocumentChunk], **kwargs: float
    ) -> SpecializedRetriever:
        index = ChromaIndex(
            ".", collection_name=f"focused-{uuid.uuid4().hex}", persistent=False
        )
        index.replace(chunks)
        return cls(index, **kwargs)

    def retrieve(self, query: str, *, agent: AgentRole) -> list[RetrievedEvidence]:
        domains = _DOMAINS.get(agent, set())
        if not domains:
            return self._no_match(agent, query, "agent has no specialized RAG domain")
        query_embedding, candidates = self._index.query(query, domains, self._fetch_k)
        eligible = [candidate for candidate in candidates if candidate.score >= self._min_relevance]
        selected = self._mmr(query_embedding, eligible)
        if not selected:
            return self._no_match(agent, query, "no chunk met RAG_MIN_RELEVANCE")
        evidence = [item.chunk.to_evidence(query, item.score) for item in selected]
        self.last_status = "OK"
        self.last_error = None
        self.last_sources = [item.source for item in evidence]
        return evidence

    def _mmr(
        self, query_embedding: list[float], candidates: list[IndexedCandidate]
    ) -> list[IndexedCandidate]:
        if not candidates:
            return []
        selected: list[IndexedCandidate] = []
        remaining = list(candidates)
        query_vector = np.asarray(query_embedding, dtype=float)
        while remaining and len(selected) < self._top_k:
            def value(candidate: IndexedCandidate) -> float:
                vector = np.asarray(candidate.embedding, dtype=float)
                relevance = float(np.dot(query_vector, vector))
                redundancy = max(
                    (float(np.dot(vector, np.asarray(item.embedding, dtype=float))) for item in selected),
                    default=0.0,
                )
                return 0.7 * relevance - 0.3 * redundancy

            best = max(remaining, key=value)
            selected.append(best)
            remaining.remove(best)
        return selected

    def _no_match(self, agent: AgentRole, query: str, detail: str) -> list[RetrievedEvidence]:
        self.last_status = "NO_RELEVANT_DOCS"
        self.last_sources = []
        self.last_error = WorkflowError(
            code=ErrorCode.RAG_ERROR,
            source_stage=agent.value,
            retryable=False,
            detail=f"NO_RELEVANT_DOCS: {detail}; query={query[:120]}",
            occurred_at=datetime.now(timezone.utc),
        )
        return []
