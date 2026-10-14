"""RAG Agent — retrieves relevant knowledge from the enterprise knowledge base.

Responsibilities:
  1. Formulate multiple targeted search queries from the incident context.
  2. Search architecture docs, runbooks, and historical incidents in Qdrant.
  3. De-duplicate and rank the retrieved evidence.
  4. Return structured evidence items with source citations.
"""
from __future__ import annotations

from datetime import datetime, timezone

from config import get_settings
from graph.state import AgentState, EvidenceItem
from tools.knowledge_search import (
    search_knowledge,
    search_runbooks,
    search_incidents,
    search_architecture,
)


def run_rag_search(state: AgentState) -> dict:
    """RAG agent node — searches the enterprise knowledge base."""
    now = datetime.now(tz=timezone.utc).isoformat()
    errors = list(state.get("agent_errors", []))
    audit_log = list(state.get("audit_log", []))

    service = state["service"]
    description = state["description"]
    triage_summary = state.get("triage_summary", "")
    metrics = state.get("metrics")

    # ── Build targeted queries from context ───────────────────────────────
    queries = [
        f"{service} {description}",
        f"{service} database connection pool",
        f"{service} error rate high",
    ]

    # Add metric-driven queries if pool is stressed
    if metrics and metrics.get("db_pool_utilization") and metrics["db_pool_utilization"] > 0.85:
        queries.append(f"{service} QueuePool limit exceeded connection timeout")
        queries.append("database connection pool exhaustion runbook")

    # Add queries from triage summary
    if triage_summary:
        queries.append(triage_summary[:200])

    # ── Execute searches ──────────────────────────────────────────────────
    all_evidence: list[EvidenceItem] = []
    seen_content: set[str] = set()

    try:
        for query in queries:
            results = search_knowledge(query, top_k=4, score_threshold=0.45)
            for ev in results:
                # De-duplicate by content prefix
                key = ev.content[:100]
                if key not in seen_content:
                    seen_content.add(key)
                    all_evidence.append(EvidenceItem(
                        content=ev.content,
                        source=ev.source,
                        doc_type=ev.doc_type,
                        relevance_score=ev.relevance_score,
                        citation=ev.citation,
                    ))

        # Sort by relevance and take top 8
        all_evidence.sort(key=lambda e: e["relevance_score"], reverse=True)
        all_evidence = all_evidence[:8]

    except Exception as e:
        errors.append(f"RAG search failed: {e}")

    audit_log.append({
        "timestamp": now,
        "event_type": "RAG_SEARCH_COMPLETE",
        "actor": "rag-agent",
        "summary": f"Retrieved {len(all_evidence)} knowledge chunks from {len(queries)} queries.",
        "details": {
            "queries": queries,
            "chunk_count": len(all_evidence),
            "sources": list({e["source"] for e in all_evidence}),
        },
    })

    return {
        "knowledge_evidence": all_evidence,
        "current_node": "log_analysis",
        "audit_log": audit_log,
        "agent_errors": errors,
    }
