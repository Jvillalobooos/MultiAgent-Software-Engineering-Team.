"""Markdown loading and token-aware chunking with stable provenance."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from engineering_team.contracts.models import RetrievedEvidence

EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


@dataclass(frozen=True)
class SourceDocument:
    source: str
    domain: str
    content: str
    section: str = "Document"
    version: str = "local"


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


def load_documents(directory: str | Path) -> list[SourceDocument]:
    documents: list[SourceDocument] = []
    for path in sorted(Path(directory).glob("*.md")):
        domain = _domain(path)
        for section, content in _markdown_sections(path.read_text(encoding="utf-8")):
            documents.append(SourceDocument(path.name, domain, content, section, "local"))
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


def chunk_documents(
    documents: list[SourceDocument],
    *,
    chunk_size: int = 800,
    overlap: int = 160,
    model_name: str = EMBEDDING_MODEL,
) -> list[DocumentChunk]:
    """Split the corpus by model tokens while preserving source-section metadata."""
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk size")
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    chunks: list[DocumentChunk] = []
    step = chunk_size - overlap
    for document in documents:
        token_ids = tokenizer.encode(document.content, add_special_tokens=False)
        section_key = hashlib.sha256(document.section.encode()).hexdigest()[:10]
        for index, offset in enumerate(range(0, max(len(token_ids), 1), step)):
            window = token_ids[offset : offset + chunk_size]
            if not window:
                continue
            text = tokenizer.decode(window, skip_special_tokens=True).strip()
            chunks.append(
                DocumentChunk(
                    source=document.source,
                    domain=document.domain,
                    section=document.section,
                    version=document.version,
                    chunk_id=f"{document.source}:{section_key}:{index}",
                    text=text,
                )
            )
            if offset + chunk_size >= len(token_ids):
                break
    return chunks
