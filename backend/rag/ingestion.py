"""Knowledge base ingestion pipeline.

Loads markdown documents from the data/ directory,
chunks them by document type, generates embeddings,
and upserts them into Qdrant.

Usage:
    python -m rag.ingestion                        # ingest all
    python -m rag.ingestion --doc-type runbook     # ingest only runbooks
    python -m rag.ingestion --dry-run              # preview without upserting
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
)
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Allow running as a module from the backend directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from rag.chunking import chunk_document, DocumentType
from rag.embeddings import EmbeddingClient

console = Console()

# Map data/ subdirectory names to DocumentType values
DIR_TO_DOC_TYPE: dict[str, DocumentType] = {
    "architecture": "architecture",
    "runbooks": "runbook",
    "incidents": "incident",
    "postmortems": "postmortem",
    "troubleshooting": "troubleshooting",
    "logs": "log",
}

# Supported file extensions
SUPPORTED_EXTENSIONS = {".md", ".txt", ".jsonl"}


def _content_hash(text: str) -> str:
    """Stable content hash used as point ID seed."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _deterministic_uuid(seed: str) -> str:
    """Generate a deterministic UUID from a string seed."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, seed))


def ensure_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int = EmbeddingClient.DIMENSIONS,
) -> None:
    """Create the Qdrant collection if it doesn't already exist."""
    existing = {c.name for c in client.get_collections().collections}
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        console.print(f"[green]Created collection:[/green] {collection_name}")
    else:
        console.print(f"[blue]Collection exists:[/blue] {collection_name}")


def load_documents(data_dir: Path, doc_type_filter: str | None = None) -> list[dict[str, Any]]:
    """Walk the data/ directory and load all supported documents.

    Args:
        data_dir: Root of the knowledge base (data/).
        doc_type_filter: If set, only load documents of this type.

    Returns:
        List of dicts with keys: content, source_file, doc_type, relative_path
    """
    documents: list[dict[str, Any]] = []

    for subdir, doc_type in DIR_TO_DOC_TYPE.items():
        if doc_type_filter and doc_type != doc_type_filter:
            continue

        subdir_path = data_dir / subdir
        if not subdir_path.exists():
            console.print(f"[yellow]Skipping missing directory:[/yellow] {subdir_path}")
            continue

        for file_path in sorted(subdir_path.rglob("*")):
            if file_path.suffix not in SUPPORTED_EXTENSIONS:
                continue
            if file_path.name == ".gitkeep":
                continue

            text = file_path.read_text(encoding="utf-8")
            if not text.strip():
                continue

            documents.append(
                {
                    "content": text,
                    "source_file": file_path.name,
                    "doc_type": doc_type,
                    "relative_path": str(file_path.relative_to(data_dir)),
                }
            )

    return documents


def ingest(
    data_dir: Path,
    qdrant_client: QdrantClient,
    embedder: EmbeddingClient,
    collection_name: str,
    doc_type_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Full ingestion pipeline: load -> chunk -> embed -> upsert.

    Returns:
        Summary dict with counts of documents, chunks, and upserted points.
    """
    ensure_collection(qdrant_client, collection_name)

    documents = load_documents(data_dir, doc_type_filter)
    console.print(f"\n[bold]Loaded {len(documents)} documents[/bold]")

    total_chunks = 0
    total_upserted = 0
    points_batch: list[PointStruct] = []
    BATCH_SIZE = 50

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        console=console,
    ) as progress:
        doc_task = progress.add_task("Processing documents...", total=len(documents))

        for doc in documents:
            chunks = chunk_document(doc["content"], doc["doc_type"])
            total_chunks += len(chunks)

            for idx, chunk_text in enumerate(chunks):
                if not chunk_text.strip():
                    continue

                point_id = _deterministic_uuid(
                    f"{doc['source_file']}_chunk_{idx}_{_content_hash(chunk_text)}"
                )

                payload: dict[str, Any] = {
                    "content": chunk_text,
                    "source_file": doc["source_file"],
                    "doc_type": doc["doc_type"],
                    "relative_path": doc["relative_path"],
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                }

                if not dry_run:
                    embedding = embedder.embed(chunk_text, task_type="RETRIEVAL_DOCUMENT")
                    points_batch.append(
                        PointStruct(id=point_id, vector=embedding, payload=payload)
                    )

                    if len(points_batch) >= BATCH_SIZE:
                        qdrant_client.upsert(
                            collection_name=collection_name,
                            points=points_batch,
                        )
                        total_upserted += len(points_batch)
                        points_batch = []
                else:
                    console.print(
                        f"  [dim]DRY RUN: {doc['source_file']} chunk {idx}:[/dim] "
                        f"{chunk_text[:80]}..."
                    )

            progress.advance(doc_task)

    # Flush remaining batch
    if points_batch and not dry_run:
        qdrant_client.upsert(collection_name=collection_name, points=points_batch)
        total_upserted += len(points_batch)

    stats = {
        "documents": len(documents),
        "chunks": total_chunks,
        "upserted": total_upserted if not dry_run else 0,
    }

    console.print(f"\n[bold green]Ingestion complete[/bold green]")
    console.print(f"  Documents : {stats['documents']}")
    console.print(f"  Chunks    : {stats['chunks']}")
    console.print(f"  Upserted  : {stats['upserted']}")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="AegisOps knowledge base ingestion")
    parser.add_argument(
        "--doc-type",
        choices=list(DIR_TO_DOC_TYPE.values()),
        help="Ingest only documents of this type",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print chunks without embedding or upserting",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Path to the data/ directory (default: auto-detect)",
    )
    args = parser.parse_args()

    settings = get_settings()

    # Locate data/ directory relative to backend/ or repo root
    if args.data_dir:
        data_dir = Path(args.data_dir)
    else:
        # When run as `python -m rag.ingestion` from backend/
        candidate = Path(__file__).parent.parent.parent / "data"
        if candidate.exists():
            data_dir = candidate
        else:
            console.print("[red]Could not locate data/ directory. Use --data-dir.[/red]")
            sys.exit(1)

    console.print(f"[bold]AegisOps Knowledge Base Ingestion[/bold]")
    console.print(f"Data directory  : {data_dir}")
    console.print(f"Qdrant URL      : {settings.qdrant_url}")
    console.print(f"Collection      : {settings.qdrant_collection}")
    console.print(f"Embedding model : {settings.embedding_model}")
    console.print(f"Dry run         : {args.dry_run}")
    console.print()

    qdrant = QdrantClient(url=settings.qdrant_url)
    embedder = EmbeddingClient(
        api_key=settings.google_api_key,
        model=settings.embedding_model,
    )

    ingest(
        data_dir=data_dir,
        qdrant_client=qdrant,
        embedder=embedder,
        collection_name=settings.qdrant_collection,
        doc_type_filter=args.doc_type,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
