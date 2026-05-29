"""Embedding service for the Agent system.

Provides text embedding for vector search and similarity matching.
"""

from __future__ import annotations

import random
from pydantic import BaseModel, Field
from typing import Any

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class EmbeddingResult(BaseModel):
    """Result of an embedding operation."""

    text: str
    embedding: list[float]
    model: str
    dimensions: int
    token_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "text_preview": self.text[:100],
            "embedding_dimensions": self.dimensions,
            "model": self.model,
            "token_count": self.token_count,
        }


# ---------------------------------------------------------------------------
# Embedding Service
# ---------------------------------------------------------------------------


class EmbeddingService:
    """Service for generating text embeddings.

    Supports multiple providers:
    - OpenAI (text-embedding-3-small, text-embedding-3-large)
    - Local fallback (random for development)

    In production, uses OpenAI API. Falls back to local embeddings
    when API key is not available.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self.dimensions = dimensions
        self.api_key = api_key or settings.openai_api_key
        self._fallback_mode = not bool(self.api_key)

        if self._fallback_mode:
            logger.warning(
                "Embedding service running in fallback mode (no API key)"
            )

    async def embed(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            EmbeddingResult with vector.
        """
        if not text.strip():
            return EmbeddingResult(
                text=text,
                embedding=[0.0] * self.dimensions,
                model=self.model,
                dimensions=self.dimensions,
                token_count=0,
            )

        if self._fallback_mode:
            return await self._embed_fallback(text)

        return await self._embed_openai(text)

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of EmbeddingResult objects.
        """
        if not texts:
            return []

        if self._fallback_mode:
            return [await self._embed_fallback(t) for t in texts]

        return await self._embed_openai_batch(texts)

    async def similarity(
        self, embedding1: list[float], embedding2: list[float]
    ) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector.
            embedding2: Second embedding vector.

        Returns:
            Cosine similarity score (-1.0 to 1.0).
        """
        if len(embedding1) != len(embedding2):
            raise ValueError("Embeddings must have same dimensions")

        dot = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = sum(a * a for a in embedding1) ** 0.5
        norm2 = sum(b * b for b in embedding2) ** 0.5

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot / (norm1 * norm2)

    async def _embed_fallback(self, text: str) -> EmbeddingResult:
        """Fallback embedding using deterministic random values.

        Generates a pseudo-random embedding based on text hash
        for consistent results across calls.
        """
        import hashlib

        # Seed random with text hash for consistency
        text_hash = hashlib.md5(text.encode()).hexdigest()
        seed = int(text_hash, 16) % (2**32)
        rng = random.Random(seed)

        embedding = [rng.uniform(-1, 1) for _ in range(self.dimensions)]

        # Normalize
        norm = sum(x * x for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]

        token_count = len(text) // 4  # rough estimate

        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model=f"{self.model} (fallback)",
            dimensions=self.dimensions,
            token_count=token_count,
        )

    async def _embed_openai(self, text: str) -> EmbeddingResult:
        """Generate embedding using OpenAI API."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": text,
                        "model": self.model,
                        "dimensions": self.dimensions,
                    },
                )
                response.raise_for_status()
                data = response.json()

                embedding = data["data"][0]["embedding"]
                tokens = data["usage"]["total_tokens"]

                return EmbeddingResult(
                    text=text,
                    embedding=embedding,
                    model=self.model,
                    dimensions=len(embedding),
                    token_count=tokens,
                )

        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}, falling back")
            return await self._embed_fallback(text)

    async def _embed_openai_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts using OpenAI API."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": texts,
                        "model": self.model,
                        "dimensions": self.dimensions,
                    },
                )
                response.raise_for_status()
                data = response.json()

                results = []
                for i, item in enumerate(data["data"]):
                    results.append(
                        EmbeddingResult(
                            text=texts[i],
                            embedding=item["embedding"],
                            model=self.model,
                            dimensions=len(item["embedding"]),
                            token_count=0,
                        )
                    )
                return results

        except Exception as e:
            logger.error(f"OpenAI batch embedding error: {e}, falling back")
            return [await self._embed_fallback(t) for t in texts]


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
