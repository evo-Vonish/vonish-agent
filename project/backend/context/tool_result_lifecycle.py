"""Tool Result Lifecycle for Context OS v2.

Implements a five-stage lifecycle for tool results:

    FULL (100 % tokens, complete content)
      -> SUMMARY (10-30 % tokens, key information)
      -> REFERENCE (<1 % tokens, ID + summary + storage_uri)
      -> ARCHIVED (0 % tokens in context, stored externally)
      -> EVICTED (deleted)

Key design principles:
    - Every REFERENCE/ARCHIVED result is recoverable (storage_uri + content_hash).
    - Per-tool-type compression strategies maximise information retention.
    - Reverse recovery allows re-hydrating compressed results on demand.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lifecycle Stage Enum
# ---------------------------------------------------------------------------


class LifecycleStage(str, Enum):
    """Five-stage lifecycle for tool results."""

    FULL = "full"          # 100 % tokens — complete content
    SUMMARY = "summary"    # 10-30 % tokens — key information summary
    REFERENCE = "reference"  # <1 % tokens — reference ID + summary
    ARCHIVED = "archived"    # 0 % tokens in context, stored externally
    EVICTED = "evicted"      # Deleted, unrecoverable


# ---------------------------------------------------------------------------
# Tool Result Reference (must be recoverable)
# ---------------------------------------------------------------------------


class ToolResultReference(BaseModel):
    """Reference descriptor that allows full recovery of a tool result.

    Every REFERENCE or ARCHIVED stage result must carry one of these so
    the original content can be retrieved on demand.
    """

    tool_result_id: str
    tool_name: str
    summary: str
    storage_uri: str = Field(
        ...,
        description="URI that resolves to the full content (e.g. storage://tool-results/xxx)",
    )
    content_hash: str = Field(
        ...,
        description="SHA-256 hash of the full content for integrity verification",
    )
    can_restore: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("content_hash")
    @classmethod
    def _hash_nonempty(cls, v: str) -> str:
        if not v or len(v) < 16:
            raise ValueError("content_hash must be a valid SHA-256 hex string")
        return v

    def verify_integrity(self, content: str) -> bool:
        """Verify that *content* matches the stored content_hash.

        Args:
            content: Full content string to verify.

        Returns:
            True if the SHA-256 hash matches.
        """
        computed = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return computed == self.content_hash


# ---------------------------------------------------------------------------
# Tool Result (single tool call result)
# ---------------------------------------------------------------------------


class ToolResult(BaseModel):
    """A single tool result at a specific lifecycle stage.

    Attributes:
        id: Unique identifier.
        tool_name: Name of the tool that produced this result.
        call_id: Tool call ID from the model.
        content: The actual content (full, summary, or reference text).
        stage: Current lifecycle stage.
        token_count: Estimated token count of content.
        reference: Recoverable reference (set when stage >= REFERENCE).
        created_at: UTC creation time.
        turn_index: Conversation turn when this result was produced.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    call_id: str
    content: str = ""
    stage: LifecycleStage = LifecycleStage.FULL
    token_count: int = 0
    reference: ToolResultReference | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    turn_index: int = 0

    @field_validator("token_count")
    @classmethod
    def _nonnegative_tokens(cls, v: int) -> int:
        if v < 0:
            raise ValueError("token_count must be non-negative")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dictionary."""
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "content": self.content,
            "stage": self.stage.value,
            "token_count": self.token_count,
            "reference": self.reference.to_dict() if self.reference else None,
            "created_at": self.created_at.isoformat(),
            "turn_index": self.turn_index,
        }


# ---------------------------------------------------------------------------
# Per-Tool-Type Compression Strategy
# ---------------------------------------------------------------------------

_TOOL_COMPRESSION_CONFIG: dict[str, dict[str, Any]] = {
    "read_file": {
        "strategy": "full_then_summary",
        "description": "File content is most important — keep full, then summary.",
    },
    "grep_files": {
        "strategy": "head_lines",
        "keep_lines": 500,
        "description": "Keep first N lines (most relevant matches at top).",
    },
    "exec_shell": {
        "strategy": "tail_chars",
        "keep_chars": 4096,
        "description": "Keep last N chars (most recent output is important).",
    },
    "web_search": {
        "strategy": "full",
        "description": "Search results are already concise — keep full.",
    },
    "list_dir": {
        "strategy": "full",
        "description": "Directory listings are compact — keep full.",
    },
    "fetch_url": {
        "strategy": "truncate",
        "max_tokens": 8000,
        "description": "Web pages can be very long — truncate to limit.",
    },
}


def get_tool_compression_strategy(tool_name: str) -> dict[str, Any]:
    """Get the compression strategy configuration for a tool type.

    Args:
        tool_name: Name of the tool.

    Returns:
        Strategy configuration dictionary.
    """
    return _TOOL_COMPRESSION_CONFIG.get(
        tool_name,
        {"strategy": "truncate", "max_tokens": 4000, "description": "Default: truncate."},
    )


# ---------------------------------------------------------------------------
# Tool Result Manager
# ---------------------------------------------------------------------------


class ToolResultManager:
    """Manages tool results through their five-stage lifecycle.

    Responsibilities:
        - Stage transitions (FULL -> SUMMARY -> REFERENCE -> ARCHIVED -> EVICTED)
        - Per-tool-type compression
        - Reference creation with recoverable storage_uri
        - Reverse recovery (ARCHIVED -> FULL, REFERENCE -> SUMMARY, etc.)
        - Token count tracking
    """

    # Transition triggers
    SUMMARY_AGE_THRESHOLD: int = 3       # turns before FULL -> SUMMARY
    REFERENCE_AGE_THRESHOLD: int = 10    # turns before SUMMARY -> REFERENCE
    ARCHIVE_AGE_THRESHOLD: int = 30      # turns before REFERENCE -> ARCHIVED

    def __init__(self) -> None:
        """Initialize the manager with empty storage."""
        # In-memory index of all managed results
        self._results: dict[str, ToolResult] = {}
        # Content storage: storage_uri -> full content
        self._storage: dict[str, str] = {}

    # -- Lifecycle Queries ---------------------------------------------

    def get(self, result_id: str) -> ToolResult | None:
        """Get a tool result by ID.

        Args:
            result_id: The tool result UUID.

        Returns:
            ToolResult if found, None otherwise.
        """
        return self._results.get(result_id)

    def list_for_conversation(
        self,
        conversation_id: str | None = None,
    ) -> list[ToolResult]:
        """List all managed results, optionally filtered by conversation.

        Args:
            conversation_id: Optional conversation filter.

        Returns:
            List of ToolResult instances.
        """
        results = list(self._results.values())
        if conversation_id:
            # Filter by prefix on the call_id or storage_uri
            results = [
                r for r in results
                if conversation_id in r.call_id or (r.reference and conversation_id in r.reference.storage_uri)
            ]
        return results

    def total_token_count(self, result_ids: list[str] | None = None) -> int:
        """Sum the token counts of managed results.

        Args:
            result_ids: Optional subset of result IDs. If None, all results.

        Returns:
            Total estimated token count.
        """
        if result_ids is None:
            result_ids = list(self._results.keys())
        return sum(self._results[rid].token_count for rid in result_ids if rid in self._results)

    # -- Registration --------------------------------------------------

    def register(self, result: ToolResult, store_full_content: bool = True) -> ToolResult:
        """Register a new tool result and index it.

        Args:
            result: The ToolResult to register.
            store_full_content: If True, store the full content for later recovery.

        Returns:
            The registered ToolResult.
        """
        self._results[result.id] = result

        if store_full_content and result.content:
            storage_uri = f"storage://tool-results/{result.id}"
            self._storage[storage_uri] = result.content

            # Auto-create reference if not present
            if result.reference is None:
                result.reference = self._create_reference(result)

        logger.debug(
            "Registered tool result",
            extra={
                "result_id": result.id,
                "tool_name": result.tool_name,
                "stage": result.stage.value,
                "tokens": result.token_count,
            },
        )
        return result

    # -- Stage Transitions ---------------------------------------------

    async def advance_stage(
        self,
        result_id: str,
        target_stage: LifecycleStage,
        max_tool_result_tokens: int = 8000,
    ) -> ToolResult:
        """Advance a tool result to a target lifecycle stage.

        Args:
            result_id: The tool result to advance.
            target_stage: Target stage (must be same or later in lifecycle).
            max_tool_result_tokens: Max tokens for FULL/SUMMARY stages.

        Returns:
            Updated ToolResult.

        Raises:
            ValueError: If target_stage is earlier than current stage.
        """
        result = self._results.get(result_id)
        if result is None:
            raise ValueError(f"ToolResult not found: {result_id}")

        stage_order = [
            LifecycleStage.FULL,
            LifecycleStage.SUMMARY,
            LifecycleStage.REFERENCE,
            LifecycleStage.ARCHIVED,
            LifecycleStage.EVICTED,
        ]
        current_idx = stage_order.index(result.stage)
        target_idx = stage_order.index(target_stage)

        if target_idx < current_idx:
            raise ValueError(
                f"Cannot regress from {result.stage.value} to {target_stage.value}"
            )

        # Apply transitions step by step
        for stage in stage_order[current_idx + 1 : target_idx + 1]:
            result = await self._apply_transition(result, stage, max_tool_result_tokens)

        self._results[result_id] = result
        return result

    async def _apply_transition(
        self,
        result: ToolResult,
        target: LifecycleStage,
        max_tool_result_tokens: int,
    ) -> ToolResult:
        """Apply a single lifecycle transition."""
        if target == LifecycleStage.SUMMARY:
            result = await self._to_summary(result, max_tool_result_tokens)
        elif target == LifecycleStage.REFERENCE:
            result = await self._to_reference(result)
        elif target == LifecycleStage.ARCHIVED:
            result = await self._to_archived(result)
        elif target == LifecycleStage.EVICTED:
            result = await self._to_evicted(result)

        result.stage = target
        return result

    async def _to_summary(
        self, result: ToolResult, max_tool_result_tokens: int
    ) -> ToolResult:
        """FULL -> SUMMARY: apply per-tool-type compression."""
        strategy = get_tool_compression_strategy(result.tool_name)
        strategy_name: str = strategy["strategy"]

        content = result.content
        summary = content

        if strategy_name == "full_then_summary":
            # Keep full if within budget, else generate summary
            if result.token_count > max_tool_result_tokens:
                summary = self._generate_summary(content, ratio=0.3)
        elif strategy_name == "head_lines":
            keep_lines: int = strategy.get("keep_lines", 500)
            summary = self._keep_head_lines(content, keep_lines)
        elif strategy_name == "tail_chars":
            keep_chars: int = strategy.get("keep_chars", 4096)
            summary = self._keep_tail_chars(content, keep_chars)
        elif strategy_name == "full":
            summary = content  # Already compact
        elif strategy_name == "truncate":
            max_tokens: int = strategy.get("max_tokens", 4000)
            summary = self._truncate_to_tokens(content, max_tokens)
        else:
            summary = self._generate_summary(content, ratio=0.2)

        result.content = summary
        result.token_count = self._estimate_tokens(summary)
        return result

    async def _to_reference(self, result: ToolResult) -> ToolResult:
        """SUMMARY -> REFERENCE: replace content with minimal reference."""
        ref = result.reference or self._create_reference(result)
        result.reference = ref

        # Replace content with a tiny reference string
        result.content = (
            f"[ToolResult {ref.tool_result_id}: {result.tool_name}]\n"
            f"Summary: {ref.summary}"
        )
        result.token_count = self._estimate_tokens(result.content)
        return result

    async def _to_archived(self, result: ToolResult) -> ToolResult:
        """REFERENCE -> ARCHIVED: content is zeroed, full data in storage."""
        ref = result.reference or self._create_reference(result)
        result.reference = ref

        # Zero out in-context content
        result.content = f"[ARCHIVED: {ref.tool_result_id} — use storage_uri to restore]"
        result.token_count = 0
        return result

    async def _to_evicted(self, result: ToolResult) -> ToolResult:
        """ARCHIVED -> EVICTED: remove from memory (storage may be kept)."""
        result.content = "[EVICTED]"
        result.token_count = 0
        result.reference = None  # Drop reference too
        self._results.pop(result.id, None)
        return result

    # -- Reverse Recovery ----------------------------------------------

    async def restore(self, result_id: str, target_stage: LifecycleStage = LifecycleStage.FULL) -> ToolResult:
        """Reverse-recover a tool result to an earlier stage.

        Paths:
            - ARCHIVED -> FULL: load from storage_uri
            - REFERENCE -> SUMMARY: restore from stored summary
            - SUMMARY -> FULL: load from storage_uri

        Args:
            result_id: Tool result to restore.
            target_stage: Desired stage (must be earlier in lifecycle).

        Returns:
            Restored ToolResult.

        Raises:
            ValueError: If result not found or recovery not possible.
        """
        result = self._results.get(result_id)
        if result is None:
            raise ValueError(f"Cannot restore unknown result: {result_id}")

        stage_order = [
            LifecycleStage.FULL,
            LifecycleStage.SUMMARY,
            LifecycleStage.REFERENCE,
            LifecycleStage.ARCHIVED,
            LifecycleStage.EVICTED,
        ]
        current_idx = stage_order.index(result.stage)
        target_idx = stage_order.index(target_stage)

        if target_idx >= current_idx:
            raise ValueError(
                f"Restore target {target_stage.value} must be earlier than current {result.stage.value}"
            )

        # Try to load full content from storage
        full_content = None
        if result.reference:
            full_content = self._storage.get(result.reference.storage_uri)

        if full_content is None:
            raise ValueError(
                f"Cannot restore {result_id}: full content not available in storage"
            )

        if target_stage == LifecycleStage.FULL:
            result.content = full_content
            result.token_count = self._estimate_tokens(full_content)
        elif target_stage == LifecycleStage.SUMMARY:
            result.content = self._generate_summary(full_content, ratio=0.3)
            result.token_count = self._estimate_tokens(result.content)

        result.stage = target_stage
        self._results[result_id] = result
        return result

    # -- Auto-advancement (age-based) ----------------------------------

    async def auto_advance(
        self,
        profile,
        current_turn: int,
    ) -> list[ToolResult]:
        """Automatically advance results based on age thresholds and profile.

        Args:
            profile: ContextProfile with max_tool_result_tokens, tool_result_mode.
            current_turn: Current conversation turn index.

        Returns:
            List of ToolResult instances that were modified.
        """
        from context.context_profile import ContextProfile

        if not isinstance(profile, ContextProfile):
            raise TypeError(f"profile must be ContextProfile, got {type(profile).__name__}")

        modified: list[ToolResult] = []

        for result in list(self._results.values()):
            age = current_turn - result.turn_index
            if age < 0:
                continue

            if result.stage == LifecycleStage.FULL:
                if age > self.SUMMARY_AGE_THRESHOLD or profile.tool_result_mode == "summary":
                    updated = await self.advance_stage(
                        result.id, LifecycleStage.SUMMARY, profile.max_tool_result_tokens
                    )
                    modified.append(updated)

            elif result.stage == LifecycleStage.SUMMARY:
                if age > self.REFERENCE_AGE_THRESHOLD or profile.tool_result_mode == "summary":
                    updated = await self.advance_stage(
                        result.id, LifecycleStage.REFERENCE, profile.max_tool_result_tokens
                    )
                    modified.append(updated)

            elif result.stage == LifecycleStage.REFERENCE:
                if age > self.ARCHIVE_AGE_THRESHOLD:
                    updated = await self.advance_stage(
                        result.id, LifecycleStage.ARCHIVED, profile.max_tool_result_tokens
                    )
                    modified.append(updated)

        return modified

    # -- Content Storage -----------------------------------------------

    def store_content(self, result_id: str, content: str) -> str:
        """Store full content and return a storage URI.

        Args:
            result_id: Tool result ID.
            content: Full content string.

        Returns:
            storage_uri for later retrieval.
        """
        storage_uri = f"storage://tool-results/{result_id}"
        self._storage[storage_uri] = content
        return storage_uri

    def retrieve_content(self, storage_uri: str) -> str | None:
        """Retrieve full content by storage URI.

        Args:
            storage_uri: URI returned by store_content().

        Returns:
            Full content string, or None if not found.
        """
        return self._storage.get(storage_uri)

    # -- Internal helpers ----------------------------------------------

    def _create_reference(self, result: ToolResult) -> ToolResultReference:
        """Create a recoverable reference for a tool result."""
        storage_uri = f"storage://tool-results/{result.id}"
        full_content = self._storage.get(storage_uri, result.content)
        content_hash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()

        summary = self._generate_summary(result.content, ratio=0.1)

        return ToolResultReference(
            tool_result_id=result.id,
            tool_name=result.tool_name,
            summary=summary,
            storage_uri=storage_uri,
            content_hash=content_hash,
            can_restore=True,
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count: ~4 chars/token."""
        if not text:
            return 0
        return max(1, len(str(text)) // 4)

    def _generate_summary(self, content: str, ratio: float = 0.2) -> str:
        """Generate a simple summary by truncation + key point extraction.

        Args:
            content: Full content.
            ratio: Target compression ratio (0.0-1.0).

        Returns:
            Summarised content.
        """
        if not content:
            return "[Empty result]"

        target_chars = max(100, int(len(content) * ratio * 4))

        # Try extracting key lines
        lines = content.split("\n")
        key_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ", "## ", "### ", "> ")):
                key_lines.append(stripped)
            elif any(kw in stripped.lower() for kw in ("result:", "summary:", "total:", "found:", "error:")):
                key_lines.append(stripped)

        if key_lines:
            summary = "\n".join(key_lines[:50])
            if len(summary) > target_chars:
                summary = summary[:target_chars] + "..."
            return summary

        # Fallback: simple truncation with ellipsis
        if len(content) > target_chars:
            return content[:target_chars] + "\n\n[...truncated]"
        return content

    @staticmethod
    def _keep_head_lines(content: str, keep_lines: int) -> str:
        """Keep first N lines of content."""
        lines = content.split("\n")
        if len(lines) <= keep_lines:
            return content
        kept = lines[:keep_lines]
        return "\n".join(kept) + f"\n\n[...{len(lines) - keep_lines} more lines]"

    @staticmethod
    def _keep_tail_chars(content: str, keep_chars: int) -> str:
        """Keep last N characters of content."""
        if len(content) <= keep_chars:
            return content
        tail = content[-keep_chars:]
        return f"[...{len(content) - keep_chars} chars omitted...]\n{tail}"

    @staticmethod
    def _truncate_to_tokens(content: str, max_tokens: int) -> str:
        """Truncate content to approximately max_tokens."""
        max_chars = max_tokens * 4
        if len(content) <= max_chars:
            return content
        # Try to cut at a newline
        truncated = content[:max_chars]
        last_nl = truncated.rfind("\n")
        if last_nl > max_chars * 0.5:
            truncated = truncated[:last_nl]
        return truncated.strip() + "\n\n[...truncated]"


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_tool_result_manager: ToolResultManager | None = None


def get_tool_result_manager() -> ToolResultManager:
    """Get the global ToolResultManager instance."""
    global _tool_result_manager
    if _tool_result_manager is None:
        _tool_result_manager = ToolResultManager()
    return _tool_result_manager
