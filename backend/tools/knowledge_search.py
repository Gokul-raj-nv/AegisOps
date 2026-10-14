"""Knowledge search tool — wraps the RAG retriever for agent use.

Agents call search_knowledge() and get back structured evidence objects
with source citations ready to include in a diagnosis.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from qdrant_client import QdrantClient

from config import get_settings
from rag.embeddings import EmbeddingClient
from rag.retrieval import KnowledgeRetriever, RetrievedChunk


@dataclass
class KnowledgeEvidence:
    """A piece of retrieved knowledge evidence, ready for agent consumption."""

    content: str
    source: str
    doc_type: str
    relevance_score: float
    citation: str

    @classmethod
    def from_chunk(cls, chunk: RetrievedChunk) -> "KnowledgeEvidence":
        return cls(
            content=chunk.content,
            source=chunk.source_file,
            doc_type=chunk.doc_type,
            relevance_score=chunk.score,
            citation=chunk.citation(),
        )

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "source": self.source,
            "doc_type": self.doc_type,
            "relevance_score": self.relevance_score,
            "citation": self.citation,
        }


def _make_retriever() -> KnowledgeRetriever:
    """Build a KnowledgeRetriever from the current settings."""
    settings = get_settings()
    qdrant = QdrantClient(url=settings.qdrant_url)
    embedder = EmbeddingClient(
        api_key=settings.google_api_key,
        model=settings.embedding_model,
    )
    return KnowledgeRetriever(
        qdrant_client=qdrant,
        embedding_client=embedder,
        collection_name=settings.qdrant_collection,
    )


def search_knowledge(
    query: str,
    top_k: int = 5,
    doc_types: list[str] | None = None,
    score_threshold: float = 0.5,
) -> list[KnowledgeEvidence]:
    """Search the enterprise knowledge base and return structured evidence.

    This is the primary tool used by the RAG Agent and Diagnosis Agent.

    Args:
        query: Natural-language query (e.g., 'database connection pool exhaustion fix').
        top_k: Max results to return.
        doc_types: Optional filter — e.g., ['runbook', 'incident', 'postmortem'].
        score_threshold: Minimum cosine similarity to include a result.

    Returns:
        List of KnowledgeEvidence sorted by relevance score (descending).
    """
    retriever = _make_retriever()
    chunks = retriever.retrieve(
        query=query,
        top_k=top_k,
        doc_types=doc_types,
        score_threshold=score_threshold,
    )
    return [KnowledgeEvidence.from_chunk(c) for c in chunks]


def search_runbooks(query: str, top_k: int = 3) -> list[KnowledgeEvidence]:
    """Convenience: search only runbooks."""
    return search_knowledge(query, top_k=top_k, doc_types=["runbook"])


def search_incidents(query: str, top_k: int = 3) -> list[KnowledgeEvidence]:
    """Convenience: search historical incidents and postmortems."""
    return search_knowledge(query, top_k=top_k, doc_types=["incident", "postmortem"])


def search_architecture(query: str, top_k: int = 3) -> list[KnowledgeEvidence]:
    """Convenience: search architecture documentation."""
    return search_knowledge(query, top_k=top_k, doc_types=["architecture"])
