"""Memory Selector for Context OS v2 (simplified).

Provides a simplified user-memory recall mechanism:

    1. Structured query by user_id + memory type
    2. Semantic similarity sorting (cosine similarity on embeddings)
    3. Top-K retrieval controlled by profile.memory_top_k

This is a lightweight alternative to the full Mem0-style semantic memory
pipeline. The full hybrid (vector + BM25 + RRF) implementation is kept in
``memory_selector_full.py`` for future use.

Memory types:
    - profile:     Static user attributes (role, tech background)
    - preference:  Dynamic preferences (model, style, format)
    - project:     Active project context (tech stack, files, todos)
    - fact:        Extracted factual information
"""

from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# User Memory Model
# ---------------------------------------------------------------------------

MemoryType = Literal["profile", "preference", "project", "fact"]


class UserMemory(BaseModel):
    """A single piece of user memory.

    Attributes:
        id: Unique memory identifier.
        user_id: Owner user identifier.
        type: Memory category (profile / preference / project / fact).
        content: Human-readable memory content.
        confidence: Confidence score (0.0-1.0).
        source: Source conversation or mechanism.
        created_at: UTC creation timestamp.
        updated_at: UTC last-update timestamp.
        access_count: Number of times this memory was recalled.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    type: MemoryType = "fact"
    content: str = Field(..., min_length=1)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = Field(default=0, ge=0)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    def touch(self) -> None:
        """Bump access_count and update updated_at."""
        self.access_count += 1
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "content": self.content,
            "confidence": round(self.confidence, 4),
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "access_count": self.access_count,
        }

    def format_for_context(self) -> str:
        """Format this memory for injection into the system prompt.

        Returns:
            A single-line or multi-line formatted string.
        """
        return f"[{self.type}] {self.content}"


# ---------------------------------------------------------------------------
# Memory Recall Result
# ---------------------------------------------------------------------------


class MemoryRecallResult(BaseModel):
    """Result of a memory recall operation."""

    memories: list[UserMemory] = Field(default_factory=list)
    query: str = ""
    total_available: int = 0
    recall_time_ms: float = 0.0

    @property
    def recalled_count(self) -> int:
        """Number of memories actually recalled."""
        return len(self.memories)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memories": [m.to_dict() for m in self.memories],
            "query": self.query,
            "total_available": self.total_available,
            "recalled_count": self.recalled_count,
            "recall_time_ms": round(self.recall_time_ms, 2),
        }

    def format_for_context(self) -> str:
        """Format all recalled memories for system prompt injection.

        Returns:
            Formatted text block, or empty string if no memories.
        """
        if not self.memories:
            return ""
        lines = ["## User Memories"]
        for mem in self.memories:
            lines.append(f"- {mem.format_for_context()}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# In-Memory Storage (simplified, replace with DB in production)
# ---------------------------------------------------------------------------


class _MemoryStore:
    """Simple in-memory store for user memories.

    In production this should be backed by PostgreSQL + a vector store.
    """

    def __init__(self) -> None:
        self._memories: dict[str, UserMemory] = {}

    def add(self, memory: UserMemory) -> UserMemory:
        """Add or update a memory."""
        self._memories[memory.id] = memory
        return memory

    def get(self, memory_id: str) -> UserMemory | None:
        """Get a memory by ID."""
        return self._memories.get(memory_id)

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        return self._memories.pop(memory_id, None) is not None

    def query_by_user(
        self,
        user_id: str,
        types: list[MemoryType] | None = None,
    ) -> list[UserMemory]:
        """Query memories by user_id and optionally by type."""
        results = [
            m for m in self._memories.values()
            if m.user_id == user_id
        ]
        if types:
            results = [m for m in results if m.type in types]
        return results

    def query_all(self) -> list[UserMemory]:
        """Return all stored memories."""
        return list(self._memories.values())

    def count_for_user(self, user_id: str) -> int:
        """Count memories for a user."""
        return sum(1 for m in self._memories.values() if m.user_id == user_id)


# ---------------------------------------------------------------------------
# Memory Selector
# ---------------------------------------------------------------------------


class MemorySelector:
    """Selects relevant user memories for context injection.

    Simplified recall mechanism:
        1. Structured query by user_id + type
        2. Semantic similarity via keyword overlap (cosine in production)
        3. Top-K controlled by profile (Cheap:5, Balanced:12, Max:30)
    """

    def __init__(self) -> None:
        """Initialize the memory selector with an in-memory store."""
        self._store = _MemoryStore()
        self._embedding_dimension = 1536
        self._min_relevance_threshold = 0.15

    # -- Public API ----------------------------------------------------

    async def recall(
        self,
        user_id: str,
        query: str,
        profile,
        memory_types: list[MemoryType] | None = None,
    ) -> MemoryRecallResult:
        """Recall relevant user memories.

        Pipeline:
            1. Query all memories for user_id (optionally filtered by type)
            2. Score by semantic relevance to the query
            3. Sort by score descending
            4. Return top-K (controlled by profile.memory_top_k)

        Args:
            user_id: User identifier.
            query: Current user query for relevance ranking.
            profile: ContextProfile with memory_top_k.
            memory_types: Optional filter by memory type.

        Returns:
            MemoryRecallResult with selected memories.
        """
        from context.context_profile import ContextProfile

        if not isinstance(profile, ContextProfile):
            raise TypeError(f"profile must be ContextProfile, got {type(profile).__name__}")

        t_start = time.perf_counter()

        # Step 1: Structured query
        all_memories = self._store.query_by_user(user_id, memory_types)
        total_available = len(all_memories)

        if not all_memories:
            return MemoryRecallResult(
                memories=[],
                query=query,
                total_available=0,
                recall_time_ms=0.0,
            )

        # Step 2: Score by relevance
        scored = self._score_memories(all_memories, query)

        # Step 3: Sort and take top-K
        scored.sort(key=lambda x: x[1], reverse=True)
        top_k = profile.memory_top_k

        selected: list[UserMemory] = []
        for memory, score in scored:
            if len(selected) >= top_k:
                break
            if score >= self._min_relevance_threshold:
                memory.touch()
                selected.append(memory)

        t_end = time.perf_counter()
        elapsed_ms = (t_end - t_start) * 1000

        return MemoryRecallResult(
            memories=selected,
            query=query,
            total_available=total_available,
            recall_time_ms=elapsed_ms,
        )

    async def recall_by_type(
        self,
        user_id: str,
        memory_type: MemoryType,
        profile,
    ) -> MemoryRecallResult:
        """Recall memories of a specific type.

        Args:
            user_id: User identifier.
            memory_type: Memory type to filter by.
            profile: ContextProfile with memory_top_k.

        Returns:
            MemoryRecallResult with matching memories.
        """
        return await self.recall(
            user_id=user_id,
            query="",  # No semantic filtering
            profile=profile,
            memory_types=[memory_type],
        )

    # -- Memory Management ---------------------------------------------

    def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: MemoryType = "fact",
        confidence: float = 0.8,
        source: str = "",
    ) -> UserMemory:
        """Add a new user memory.

        Args:
            user_id: User identifier.
            content: Memory content.
            memory_type: Type of memory.
            confidence: Confidence score (0.0-1.0).
            source: Source of the memory.

        Returns:
            The created UserMemory.
        """
        memory = UserMemory(
            user_id=user_id,
            type=memory_type,
            content=content,
            confidence=confidence,
            source=source,
        )
        self._store.add(memory)
        logger.debug(
            "Added user memory",
            extra={
                "user_id": user_id,
                "type": memory_type,
                "content_preview": content[:80],
            },
        )
        return memory

    def get_memory(self, memory_id: str) -> UserMemory | None:
        """Get a memory by ID.

        Args:
            memory_id: Memory UUID.

        Returns:
            UserMemory if found, None otherwise.
        """
        return self._store.get(memory_id)

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID.

        Args:
            memory_id: Memory UUID.

        Returns:
            True if the memory was deleted.
        """
        return self._store.delete(memory_id)

    def list_memories(self, user_id: str) -> list[UserMemory]:
        """List all memories for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of UserMemory instances.
        """
        return self._store.query_by_user(user_id)

    # -- Scoring -------------------------------------------------------

    def _score_memories(
        self,
        memories: list[UserMemory],
        query: str,
    ) -> list[tuple[UserMemory, float]]:
        """Score memories by relevance to the query.

        Uses a simple keyword-overlap scorer as a baseline.
        In production, replace with embedding-based cosine similarity.

        Args:
            memories: List of memories to score.
            query: Query string.

        Returns:
            List of (memory, score) tuples.
        """
        if not query:
            # No query: score by confidence and recency
            now = datetime.now(timezone.utc)
            results = []
            for mem in memories:
                age_hours = (now - mem.updated_at).total_seconds() / 3600.0
                recency_score = math.exp(-age_hours / 168.0)  # 1-week halflife
                score = 0.5 * mem.confidence + 0.5 * recency_score
                results.append((mem, score))
            return results

        query_terms = set(query.lower().split())
        if not query_terms:
            return [(mem, 0.5) for mem in memories]

        results = []
        for mem in memories:
            mem_lower = mem.content.lower()
            mem_terms = set(mem_lower.split())

            # Jaccard similarity
            intersection = query_terms & mem_terms
            union = query_terms | mem_terms
            jaccard = len(intersection) / len(union) if union else 0.0

            # Boost exact phrase matches
            phrase_boost = 0.2 if query.lower() in mem_lower else 0.0

            # Boost by memory type relevance
            type_boost = 0.1 if mem.type in ("project", "preference") else 0.0

            score = min(1.0, jaccard + phrase_boost + type_boost + 0.1)
            results.append((mem, score))

        return results

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Args:
            a: First embedding vector.
            b: Second embedding vector.

        Returns:
            Cosine similarity (0.0 to 1.0 for non-negative vectors).
        """
        if len(a) != len(b):
            logger.warning(f"Embedding dimension mismatch: {len(a)} vs {len(b)}")
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def set_threshold(self, threshold: float) -> None:
        """Set the minimum relevance threshold for recall.

        Args:
            threshold: Minimum relevance score (0.0 to 1.0).
        """
        self._min_relevance_threshold = max(0.0, min(1.0, threshold))

    @property
    def min_relevance_threshold(self) -> float:
        """Get the current minimum relevance threshold."""
        return self._min_relevance_threshold


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_memory_selector: MemorySelector | None = None


def get_memory_selector() -> MemorySelector:
    """Get the global MemorySelector instance."""
    global _memory_selector
    if _memory_selector is None:
        _memory_selector = MemorySelector()
    return _memory_selector
