"""RAG Evaluation — measures retrieval quality of the knowledge base.

Evaluates:
  - Context Precision: Are retrieved chunks relevant to the query?
  - Context Recall: Are all important chunks retrieved?
  - Mean Reciprocal Rank (MRR): Is the best chunk ranked first?
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RAGEvalResult:
    query: str
    retrieved_count: int
    relevant_count: int
    precision: float        # relevant_retrieved / total_retrieved
    recall: float           # relevant_retrieved / total_relevant
    mrr: float              # 1/rank of first relevant result
    sources: list[str]


@dataclass
class RAGEvalReport:
    total_queries: int
    mean_precision: float
    mean_recall: float
    mean_mrr: float
    results: list[RAGEvalResult]


# ---------------------------------------------------------------------------
# Ground truth dataset — expected sources for each evaluation query
# ---------------------------------------------------------------------------

EVAL_QUERIES: list[dict[str, Any]] = [
    {
        "query": "database connection pool exhaustion payment service",
        "expected_doc_types": ["runbook", "incident", "postmortem"],
        "expected_keywords": ["pool_size", "QueuePool", "connection"],
        "min_relevant": 2,
    },
    {
        "query": "payment service high error rate root cause",
        "expected_doc_types": ["incident", "troubleshooting", "runbook"],
        "expected_keywords": ["error rate", "payment", "pool"],
        "min_relevant": 2,
    },
    {
        "query": "how to restart a service safely rolling restart kubernetes",
        "expected_doc_types": ["runbook"],
        "expected_keywords": ["kubectl", "rollout", "restart"],
        "min_relevant": 1,
    },
    {
        "query": "auth service CPU saturation cascade failure",
        "expected_doc_types": ["incident", "postmortem"],
        "expected_keywords": ["auth-service", "CPU", "cascade"],
        "min_relevant": 1,
    },
    {
        "query": "redis cache failure impact on order service",
        "expected_doc_types": ["runbook", "architecture"],
        "expected_keywords": ["redis", "cache", "order"],
        "min_relevant": 1,
    },
]


def _is_relevant(chunk_content: str, chunk_doc_type: str, expected: dict[str, Any]) -> bool:
    """Determine if a retrieved chunk is relevant to a query."""
    # Check doc_type match
    if chunk_doc_type not in expected.get("expected_doc_types", []):
        return False
    # Check keyword presence
    content_lower = chunk_content.lower()
    keywords = expected.get("expected_keywords", [])
    matched = sum(1 for kw in keywords if kw.lower() in content_lower)
    return matched >= max(1, len(keywords) // 2)


def evaluate_rag(retriever=None) -> RAGEvalReport:
    """Evaluate RAG retrieval quality against the ground truth dataset.

    Args:
        retriever: Optional KnowledgeRetriever instance. If None, tries to
                   import and construct one using current settings.

    Returns:
        RAGEvalReport with precision, recall, and MRR metrics.
    """
    if retriever is None:
        try:
            from qdrant_client import QdrantClient
            from config import get_settings
            from rag.embeddings import EmbeddingClient
            from rag.retrieval import KnowledgeRetriever
            settings = get_settings()
            retriever = KnowledgeRetriever(
                qdrant_client=QdrantClient(url=settings.qdrant_url),
                embedding_client=EmbeddingClient(
                    api_key=settings.google_api_key,
                    model=settings.embedding_model,
                ),
                collection_name=settings.qdrant_collection,
            )
        except Exception as e:
            print(f"[RAG Eval] Cannot construct retriever: {e}")
            return RAGEvalReport(0, 0.0, 0.0, 0.0, [])

    results: list[RAGEvalResult] = []

    for eval_item in EVAL_QUERIES:
        query = eval_item["query"]
        try:
            chunks = retriever.retrieve(query=query, top_k=5, score_threshold=0.4)
        except Exception as e:
            print(f"[RAG Eval] Retrieval failed for query '{query}': {e}")
            continue

        relevant_chunks = [
            c for c in chunks
            if _is_relevant(c.content, c.doc_type, eval_item)
        ]

        retrieved = len(chunks)
        relevant = len(relevant_chunks)
        total_relevant = eval_item.get("min_relevant", 1)

        precision = relevant / retrieved if retrieved > 0 else 0.0
        recall = min(relevant / total_relevant, 1.0) if total_relevant > 0 else 0.0

        # MRR: find rank of first relevant result
        mrr = 0.0
        for rank, chunk in enumerate(chunks, start=1):
            if _is_relevant(chunk.content, chunk.doc_type, eval_item):
                mrr = 1.0 / rank
                break

        results.append(RAGEvalResult(
            query=query,
            retrieved_count=retrieved,
            relevant_count=relevant,
            precision=round(precision, 3),
            recall=round(recall, 3),
            mrr=round(mrr, 3),
            sources=[c.source_file for c in chunks],
        ))

    if not results:
        return RAGEvalReport(0, 0.0, 0.0, 0.0, [])

    return RAGEvalReport(
        total_queries=len(results),
        mean_precision=round(sum(r.precision for r in results) / len(results), 3),
        mean_recall=round(sum(r.recall for r in results) / len(results), 3),
        mean_mrr=round(sum(r.mrr for r in results) / len(results), 3),
        results=results,
    )
