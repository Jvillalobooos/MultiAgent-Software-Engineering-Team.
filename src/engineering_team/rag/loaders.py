"""Markdown loading and token-aware chunking with stable provenance."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from engineering_team.contracts.models import RetrievedEvidence

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass(frozen=True)
class DocumentChunk:
    source: str
    domain: str
    section: str
    version: str
    chunk_id: str
    text: str

    def to_evidence(self, query: str, score: float | None) -> RetrievedEvidence:
        return RetrievedEvidence(
            source=self.source,
            section=self.section,
            version=self.version,
            chunk_id=self.chunk_id,
            fragment=self.text,
            domain=self.domain,
            query=query,
            score=score,
        )


def _domain(path: Path) -> str:
    name = path.stem.lower()
    if "owasp" in name:
        return "owasp"
    if "api" in name:
        return "api"
    if "architecture" in name:
        return "architecture"
    if "security" in name:
        return "security"
    if "testing" in name:
        return "testing"
    return "coding"


def _markdown_sections(text: str) -> list[tuple[str, str]]:
    headings: dict[int, str] = {}
    current_lines: list[str] = []
    current_section = "Document"
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if content:
            sections.append((current_section, content))

    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            current_lines.append(line)
            continue
        flush()
        current_lines = []
        level = len(match.group(1))
        headings[level] = match.group(2)
        for deeper in [item for item in headings if item > level]:
            del headings[deeper]
        current_section = " / ".join(headings[item] for item in sorted(headings))
    flush()
    return sections or [("Document", text.strip())]


def load_documents(directory: str | Path) -> list[Document]:
    """Load source sections into the official LangChain Document abstraction."""
    documents: list[Document] = []
    for path in sorted(Path(directory).glob("*.md")):
        domain = _domain(path)
        for section, content in _markdown_sections(path.read_text(encoding="utf-8")):
            documents.append(Document(
                page_content=content,
                metadata={
                    "source": path.name,
                    "domain": domain,
                    "section": section,
                    "version": "local",
                },
            ))
    return documents


def chunk_document(
    content: str,
    source: str,
    domain: str,
    chunk_size: int,
    overlap: int,
    *,
    section: str = "Document",
    version: str = "local",
) -> list[DocumentChunk]:
    """Compatibility character splitter; corpus ingestion uses token chunking below."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk size")
    chunks: list[DocumentChunk] = []
    offset = 0
    index = 0
    while offset < len(content):
        text = content[offset : offset + chunk_size]
        chunks.append(DocumentChunk(source, domain, section, version, f"{source}:{index}", text))
        if offset + chunk_size >= len(content):
            break
        offset += chunk_size - overlap
        index += 1
    return chunks


def build_text_splitter(
    *, chunk_size: int = 800, overlap: int = 160, model_name: str = EMBEDDING_MODEL
) -> RecursiveCharacterTextSplitter:
    """Build the Plan-frozen token-aware LangChain recursive splitter."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk size")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    return RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
        tokenizer,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        add_start_index=True,
    )


def chunk_documents(
    documents: list[Document],
    *,
    chunk_size: int = 800,
    overlap: int = 160,
    model_name: str = EMBEDDING_MODEL,
) -> list[DocumentChunk]:
    """Split the corpus by model tokens while preserving source-section metadata."""
    splitter = build_text_splitter(
        chunk_size=chunk_size, overlap=overlap, model_name=model_name
    )
    chunks: list[DocumentChunk] = []
    counters: defaultdict[tuple[str, str], int] = defaultdict(int)
    for document in splitter.split_documents(documents):
        source = str(document.metadata["source"])
        section = str(document.metadata["section"])
        section_key = hashlib.sha256(section.encode()).hexdigest()[:10]
        counter_key = (source, section)
        index = counters[counter_key]
        counters[counter_key] += 1
        chunks.append(DocumentChunk(
            source=source,
            domain=str(document.metadata["domain"]),
            section=section,
            version=str(document.metadata["version"]),
            chunk_id=f"{source}:{section_key}:{index}",
            text=document.page_content,
        ))
    return chunks
