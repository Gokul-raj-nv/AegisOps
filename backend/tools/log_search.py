"""Log search tool — searches indexed service logs for error patterns.

In Phase 1, logs are pre-loaded from data/logs/ into Qdrant.
This tool queries that index to extract relevant log evidence
(error patterns, anomalies, recurring failures) for the Log Analysis Agent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from config import get_settings
from rag.embeddings import EmbeddingClient
from rag.retrieval import KnowledgeRetriever


@dataclass
class LogEvidence:
    """A structured piece of log evidence."""

    raw_line: str
    timestamp: str | None
    level: str | None
    service: str | None
    message: str | None
    error: str | None
    extra: dict[str, Any]
    source_file: str
    relevance_score: float

    @classmethod
    def from_json_line(
        cls,
        line: str,
        source_file: str,
        relevance_score: float = 1.0,
    ) -> "LogEvidence":
        """Parse a structured JSON log line into LogEvidence."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            data = {}

        known_keys = {"timestamp", "level", "service", "message", "error"}
        extra = {k: v for k, v in data.items() if k not in known_keys}

        return cls(
            raw_line=line,
            timestamp=data.get("timestamp"),
            level=data.get("level"),
            service=data.get("service"),
            message=data.get("message"),
            error=data.get("error"),
            extra=extra,
            source_file=source_file,
            relevance_score=relevance_score,
        )

    def is_error(self) -> bool:
        return self.level in ("ERROR", "CRITICAL")

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "service": self.service,
            "message": self.message,
            "error": self.error,
            "extra": self.extra,
            "source_file": self.source_file,
            "relevance_score": self.relevance_score,
        }


def search_logs(
    query: str,
    service: str | None = None,
    top_k: int = 10,
    errors_only: bool = False,
) -> list[LogEvidence]:
    """Search log files for lines relevant to a query.

    Uses Qdrant semantic search over the logs collection.
    Falls back to scanning data/logs/ directly if Qdrant is unavailable.

    Args:
        query: What to search for (e.g., 'database connection timeout').
        service: Optional service name filter.
        top_k: Max results.
        errors_only: If True, only return ERROR/CRITICAL level lines.

    Returns:
        List of LogEvidence ordered by relevance score.
    """
    settings = get_settings()

    try:
        qdrant = QdrantClient(url=settings.qdrant_url)
        embedder = EmbeddingClient(
            api_key=settings.google_api_key,
            model=settings.embedding_model,
        )
        retriever = KnowledgeRetriever(
            qdrant_client=qdrant,
            embedding_client=embedder,
            collection_name=settings.qdrant_logs_collection,
        )
        chunks = retriever.retrieve(query=query, top_k=top_k, score_threshold=0.4)
        results = [
            LogEvidence.from_json_line(
                line=c.content,
                source_file=c.source_file,
                relevance_score=c.score,
            )
            for c in chunks
        ]
    except Exception:
        # Fallback: scan log files directly (useful when Qdrant is not seeded)
        results = _scan_log_files(query=query, service=service, max_lines=top_k * 5)

    if service:
        results = [r for r in results if r.service == service or service in (r.source_file or "")]

    if errors_only:
        results = [r for r in results if r.is_error()]

    return results[:top_k]


def _scan_log_files(
    query: str,
    service: str | None,
    max_lines: int = 100,
) -> list[LogEvidence]:
    """Direct file scan fallback — searches data/logs/*.jsonl for matching lines."""
    # Locate data/logs relative to this file
    logs_dir = Path(__file__).parent.parent.parent / "data" / "logs"
    if not logs_dir.exists():
        return []

    results: list[LogEvidence] = []
    query_lower = query.lower()

    for log_file in sorted(logs_dir.glob("*.jsonl")):
        lines = log_file.read_text(encoding="utf-8").splitlines()
        for line in lines:
            if not line.strip():
                continue
            if query_lower in line.lower():
                ev = LogEvidence.from_json_line(
                    line=line,
                    source_file=log_file.name,
                    relevance_score=0.8,  # file scan gets a fixed score
                )
                results.append(ev)
                if len(results) >= max_lines:
                    break

    return results


def get_error_summary(service: str | None = None) -> dict[str, int]:
    """Return a count of log levels from the local log files.

    Useful for the Log Analysis Agent to quickly identify error frequency.
    """
    logs_dir = Path(__file__).parent.parent.parent / "data" / "logs"
    counts: dict[str, int] = {"INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

    if not logs_dir.exists():
        return counts

    for log_file in logs_dir.glob("*.jsonl"):
        if service and service not in log_file.name:
            continue
        for line in log_file.read_text(encoding="utf-8").splitlines():
            try:
                data = json.loads(line)
                level = data.get("level", "UNKNOWN")
                counts[level] = counts.get(level, 0) + 1
            except json.JSONDecodeError:
                continue

    return counts
