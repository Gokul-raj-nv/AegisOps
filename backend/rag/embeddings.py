"""Embedding model wrapper for AegisOps.

Uses Google's text-embedding-004 model via the google-genai SDK.
All embeddings are 768-dimensional unit vectors.
"""
from __future__ import annotations

from google import genai
from google.genai import types as genai_types
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)


class EmbeddingClient:
    """Thin wrapper around Google's embedding API with retry logic."""

    DIMENSIONS = 768

    def __init__(self, api_key: str, model: str = "models/text-embedding-004") -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    def embed(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> list[float]:
        """Embed a single text string.

        Args:
            text: The text to embed.
            task_type: Google embedding task type.
                Use 'RETRIEVAL_DOCUMENT' for ingestion.
                Use 'RETRIEVAL_QUERY' for query-time embeddings.

        Returns:
            List of 768 floats representing the embedding.
        """
        result = self._client.models.embed_content(
            model=self._model,
            contents=text,
            config=genai_types.EmbedContentConfig(task_type=task_type),
        )
        return result.embeddings[0].values

    def embed_batch(
        self,
        texts: list[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 50,
    ) -> list[list[float]]:
        """Embed a list of texts in batches."""
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            for text in batch:
                embeddings.append(self.embed(text, task_type=task_type))
        return embeddings

    def embed_query(self, query: str) -> list[float]:
        """Convenience method for query-time embedding."""
        return self.embed(query, task_type="RETRIEVAL_QUERY")
