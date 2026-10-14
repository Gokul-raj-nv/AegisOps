"""Document chunking strategies for the AegisOps knowledge base."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_text_splitters import RecursiveCharacterTextSplitter


DocumentType = Literal["runbook", "architecture", "incident", "postmortem", "troubleshooting", "log"]


@dataclass
class ChunkConfig:
    chunk_size: int
    chunk_overlap: int
    separators: list[str]


# Different document types benefit from different chunking strategies.
# Runbooks have numbered steps — smaller chunks keep steps coherent.
# Architecture docs are denser — larger chunks preserve context.
_CHUNK_CONFIGS: dict[DocumentType, ChunkConfig] = {
    "runbook": ChunkConfig(
        chunk_size=512,
        chunk_overlap=64,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    ),
    "architecture": ChunkConfig(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    ),
    "incident": ChunkConfig(
        chunk_size=600,
        chunk_overlap=80,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    ),
    "postmortem": ChunkConfig(
        chunk_size=600,
        chunk_overlap=80,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    ),
    "troubleshooting": ChunkConfig(
        chunk_size=512,
        chunk_overlap=64,
        separators=["\n---", "\n## ", "\n### ", "\n\n", "\n", " "],
    ),
    "log": ChunkConfig(
        chunk_size=256,
        chunk_overlap=32,
        separators=["\n"],
    ),
}


def chunk_document(text: str, doc_type: DocumentType) -> list[str]:
    """Split a document into chunks appropriate for its type.

    Args:
        text: Raw document text.
        doc_type: Category of document to select the chunking strategy.

    Returns:
        List of text chunks ready for embedding.
    """
    config = _CHUNK_CONFIGS.get(doc_type, _CHUNK_CONFIGS["architecture"])
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
        separators=config.separators,
        length_function=len,
    )
    return splitter.split_text(text)
