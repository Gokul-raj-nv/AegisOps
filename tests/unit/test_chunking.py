"""Unit tests for the document chunking module."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from rag.chunking import chunk_document


SAMPLE_RUNBOOK = """
# Runbook: DB Pool Exhaustion

## Symptoms
HTTP 500 errors. QueuePool limit reached.

## Step 1
Check pool utilization metric.

## Step 2
Increase DB_POOL_SIZE.

## Step 3
Restart the service.
"""


def test_chunk_document_returns_list():
    chunks = chunk_document(SAMPLE_RUNBOOK, "runbook")
    assert isinstance(chunks, list)
    assert len(chunks) > 0


def test_chunk_document_non_empty_chunks():
    chunks = chunk_document(SAMPLE_RUNBOOK, "runbook")
    for chunk in chunks:
        assert chunk.strip() != ""


def test_chunk_document_respects_size():
    chunks = chunk_document(SAMPLE_RUNBOOK, "runbook")
    for chunk in chunks:
        # Each chunk should be within chunk_size + generous overlap margin
        assert len(chunk) <= 700


def test_chunk_document_different_types():
    for doc_type in ["runbook", "architecture", "incident", "postmortem", "troubleshooting", "log"]:
        chunks = chunk_document(SAMPLE_RUNBOOK, doc_type)  # type: ignore[arg-type]
        assert len(chunks) > 0


def test_chunk_document_log_type():
    log_text = "\n".join([f'{{"level": "ERROR", "msg": "error_{i}"}}' for i in range(20)])
    chunks = chunk_document(log_text, "log")
    assert len(chunks) > 0


def test_chunk_document_empty_after_strip_handled():
    """Ingestion skips empty chunks — verify chunker at least returns something for real content."""
    long_text = "Database connection pool exhausted. " * 50
    chunks = chunk_document(long_text, "runbook")
    assert len(chunks) > 0
    assert all(len(c) > 0 for c in chunks)
