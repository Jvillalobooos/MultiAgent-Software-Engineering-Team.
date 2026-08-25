"""Persistent Chroma index backed by real Sentence Transformers embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import chromadb
import numpy as np
from sentence_transformers import SentenceTransformer

from .loaders import EMBEDDING_MODEL, DocumentChunk


@lru_cache(maxsize=2)
def _embedding_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name)


@dataclass(frozen=True)
class IndexedCandidate:
    chunk: DocumentChunk
    score: float
    embedding: list[float]


class ChromaIndex:
    """Own a durable Chroma collection and its approved embedding model."""

    def __init__(
        self,
        persist_directory: str | Path,
        *,
        collection_name: str = "engineering-knowledge",
        model_name: str = EMBEDDING_MODEL,
        persistent: bool = True,
    ) -> None:
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        self.model_name = model_name
        self._model = _embedding_model(model_name)
        self._client = (
            chromadb.PersistentClient(path=str(self.persist_directory))
            if persistent
            else chromadb.EphemeralClient()
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine", "embedding_model": model_name}
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def replace(self, chunks: list[DocumentChunk]) -> None:
        current = self._collection.get(include=[]).get("ids", [])
        if current:
            self._collection.delete(ids=current)
        if not chunks:
            return
        texts = [chunk.text for chunk in chunks]
        embeddings = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        ).tolist()
        self._collection.add(
            ids=[chunk.chunk_id for chunk in chunks],
            documents=texts,
            embeddings=embeddings,
            metadatas=[
                {
                    "source": chunk.source,
                    "domain": chunk.domain,
                    "section": chunk.section,
                    "version": chunk.version,
                }
                for chunk in chunks
            ],
        )

    def query(self, query: str, domains: set[str], fetch_k: int) -> tuple[list[float], list[IndexedCandidate]]:
        if self.count == 0:
            return [], []
        query_embedding = self._model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        result = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(fetch_k, self.count),
            where={"domain": {"$in": sorted(domains)}},
            include=["documents", "metadatas", "distances", "embeddings"],
        )
        candidates: list[IndexedCandidate] = []
        for chunk_id, document, metadata, distance, embedding in zip(
            result["ids"][0],
            result["documents"][0],
            result["metadatas"][0],
            result["distances"][0],
            result["embeddings"][0],
            strict=True,
        ):
            # Chroma cosine distance is 1-cosine. Normalize cosine [-1, 1]
            # to the configured relevance scale [0, 1].
            score = max(0.0, min(1.0, 1.0 - (float(distance) / 2.0)))
            candidates.append(
                IndexedCandidate(
                    chunk=DocumentChunk(
                        source=str(metadata["source"]),
                        domain=str(metadata["domain"]),
                        section=str(metadata["section"]),
                        version=str(metadata["version"]),
                        chunk_id=chunk_id,
                        text=document,
                    ),
                    score=score,
                    embedding=np.asarray(embedding, dtype=float).tolist(),
                )
            )
        return query_embedding.tolist(), candidates
