# Real RAG pipeline

The implemented path is observable and local:

`Documents → loader → token-aware chunking → Sentence Transformers → embeddings → Chroma → specialized retriever → RetrievedEvidence → agent`.

Six non-placeholder Markdown sources under `knowledge/` are parsed by heading.
Chunks use the tokenizer for
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 800 tokens and
160-token overlap. The multilingual model grounds Spanish and English while
remaining practical for local CPU execution. Embeddings are normalized and
stored in persistent Chroma at `RAG_PERSIST_DIRECTORY`.

Retrieval uses MMR with fetch_k 8, returns top_k 4, and accepts only a
normalized cosine relevance of at least 0.55. Architecture filters
`architecture|api`, Security filters `security|owasp`, and Testing filters
`testing|coding`. All values are external settings in `.env.example`.

Each `RetrievedEvidence` contains source, section, version, chunk_id, fragment,
domain, query, retrieval timestamp and score. No match returns
`NO_RELEVANT_DOCS`, records `RAG_ERROR`, returns no source, and cannot trigger
cloud automatically. Tests cover a real semantic match, no-match, persistence
after reopening the Chroma collection, and per-agent context isolation.
