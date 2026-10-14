"""Similarity search and context retrieval from Qdrant."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient

from .embeddings import EmbeddingClient


@dataclass
class RetrievedChunk:
    """A single retrieved knowledge chunk with source metadata."""

    content: str
    source_file: str
    doc_type: str
    score: float
    chunk_index: int
    collection: str

    def citation(self) -> str:
        """Human-readable citation string."""
        return f"{self.source_file} (score: {self.score:.3f})"


class KnowledgeRetriever:
    """Retrieves relevant knowledge chunks from Qdrant.

    Each chunk is returned with its source file, document type,
    similarity score, and chunk index so downstream agents can
    cite their evidence precisely.
    """

    def __init__(
        self,
        qdrant_client: QdrantClient,
        embedding_client: EmbeddingClient,
        collection_name: str,
    ) -> None:
        self._qdrant = qdrant_client
        self._embedder = embedding_client
        self._collection = collection_name

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        doc_types: list[str] | None = None,
        score_threshold: float = 0.5,
    ) -> list[RetrievedChunk]:
        """Find the most relevant knowledge chunks for a query.

        Args:
            query: Natural language query (e.g., 'DB connection pool exhaustion fix').
            top_k: Maximum number of chunks to return.
            doc_types: If provided, filter by document type
                (e.g., ['runbook', 'incident']).
            score_threshold: Minimum cosine similarity to include.

        Returns:
            List of RetrievedChunk ordered by similarity score (descending).
        """
        query_vector = self._embedder.embed_query(query)

        search_filter = None
        if doc_types:
            from qdrant_client.models import Filter, FieldCondition, MatchAny
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="doc_type",
                        match=MatchAny(any=doc_types),
                    )
                ]
            )

        results = self._qdrant.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=search_filter,
            with_payload=True,
        )

        chunks: list[RetrievedChunk] = []
        for hit in results:
            payload: dict[str, Any] = hit.payload or {}
            chunks.append(
                RetrievedChunk(
                    content=payload.get("content", ""),
                    source_file=payload.get("source_file", "unknown"),
                    doc_type=payload.get("doc_type", "unknown"),
                    score=hit.score,
                    chunk_index=payload.get("chunk_index", 0),
                    collection=self._collection,
                )
            )
        return chunks

    def retrieve_incidents(
        self, query: str, top_k: int = 3
    ) -> list[RetrievedChunk]:
        """Convenience method: retrieve only historical incidents."""
        return self.retrieve(query, top_k=top_k, doc_types=["incident", "postmortem"])

    def retrieve_runbooks(self, query: str, top_k: int = 3) -> list[RetrievedChunk]:
        """Convenience method: retrieve only runbooks."""
        return self.retrieve(query, top_k=top_k, doc_types=["runbook"])
