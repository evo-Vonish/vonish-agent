"""Real-time context usage tracker for Context OS v2.

Queries the actual database to compute token usage, message counts,
tool call counts, and other context metrics per conversation.

Replaces the placeholder ``estimated_usage = budget * 0.6`` that was
previously used in the usage/preview endpoints.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import get_logger
from context.minimal_context import (
    MAX_CONTEXT_TOKENS,
    format_tool_result_for_context,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class ContextSnapshot:
    """Point-in-time snapshot of context usage for a conversation."""

    conversation_id: str
    profile_name: str = "balanced"
    model_id: str = "deepseek-v4-pro"

    # Token estimates (computed from real data)
    total_estimated_tokens: int = 0
    message_tokens: int = 0
    tool_result_tokens: int = 0
    system_prompt_tokens: int = 0

    # Budget info (from profile + model capability)
    max_input_tokens: int = MAX_CONTEXT_TOKENS
    context_window: int = MAX_CONTEXT_TOKENS
    output_reserved: int = 8192
    safety_margin: int = 0
    available_budget: int = 0
    usage_ratio: float = 0.0

    # Counts (from DB)
    message_count: int = 0
    user_message_count: int = 0
    tool_call_count: int = 0
    workspace_file_count: int = 0
    memory_item_count: int = 0

    # Compression
    compression_level: str = "none"
    budget_healthy: bool = True

    # Component breakdown
    components: dict[str, int] = field(default_factory=dict)

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "profile": self.profile_name,
            "model": self.model_id,
            "total_tokens": self.total_estimated_tokens,
            "max_tokens": self.max_input_tokens,
            "context_window": self.context_window,
            "output_reserved": self.output_reserved,
            "safety_margin": self.safety_margin,
            "available_budget": self.available_budget,
            "usage_ratio": round(self.usage_ratio, 4),
            "compression_level": self.compression_level,
            "budget_healthy": self.budget_healthy,
            # Counts for the frontend
            "message_count": self.message_count,
            "user_message_count": self.user_message_count,
            "tool_call_count": self.tool_call_count,
            "workspace_file_count": self.workspace_file_count,
            "memory_item_count": self.memory_item_count,
            "components": self.components,
        }

    def to_frontend_profile(self) -> dict[str, Any]:
        """Map to frontend ContextProfile shape."""
        return {
            "id": self.profile_name,
            "name": self.profile_name.capitalize(),
            "tokenBudget": self.max_input_tokens,
            "tokenUsed": self.total_estimated_tokens,
            "messageRounds": self.user_message_count,
            "memoryCount": self.memory_item_count,
            "fileCount": self.workspace_file_count,
            "toolCount": self.tool_call_count,
            "compressionLevel": self.compression_level,
        }


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

# Characters-per-token approximation used consistently across Context OS
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from text (~4 chars/token)."""
    if not text:
        return 0
    return max(1, len(str(text)) // CHARS_PER_TOKEN)


def estimate_content_tokens(content: list[dict[str, Any]] | str | None) -> int:
    """Estimate tokens from a message content block.

    Handles the content-blocks format: [{"type": "text", "text": "..."}, ...]
    """
    if content is None:
        return 0
    if isinstance(content, str):
        return estimate_tokens(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                text = block.get("text", "")
                if text:
                    total += estimate_tokens(str(text))
        return total
    return 0


def get_compression_level_for_ratio(ratio: float) -> str:
    """Determine compression level from usage ratio.

    Mirrors the five thresholds defined in token_budget.py:
        none < 70%, light < 80%, moderate < 85%, heavy < 90%,
        extreme < 99%, emergency >= 99%
    """
    if ratio >= 0.99:
        return "aggressive"
    elif ratio >= 0.90:
        return "aggressive"
    elif ratio >= 0.85:
        return "medium"
    elif ratio >= 0.80:
        return "medium"
    elif ratio >= 0.70:
        return "light"
    return "none"


# ---------------------------------------------------------------------------
# Context Tracker
# ---------------------------------------------------------------------------


class ContextTracker:
    """Tracks real context usage by querying the database.

    Instead of returning hardcoded or proportional estimates, this
    queries actual message counts, tool call records, workspace files,
    and memory items to produce a real ContextSnapshot.
    """

    def __init__(self) -> None:
        pass

    # ===================================================================
    # Main entry point: get a snapshot for a conversation
    # ===================================================================

    async def snapshot(
        self,
        conversation_id: str,
        db: AsyncSession,
        model_id: str = "deepseek-v4-pro",
        profile_name: str = "balanced",
    ) -> ContextSnapshot:
        """Build a real ContextSnapshot from database state.

        Args:
            conversation_id: The conversation UUID string.
            db: Async database session.
            model_id: Model identifier (for capability lookup).
            profile_name: Context profile name.

        Returns:
            ContextSnapshot with real counts and estimates.
        """
        snapshot = ContextSnapshot(
            conversation_id=conversation_id,
            profile_name=profile_name,
            model_id=model_id,
        )

        try:
            conv_uuid = uuid.UUID(conversation_id)
        except ValueError:
            logger.warning(f"Invalid conversation_id: {conversation_id}")
            return snapshot

        # ── Resolve model capability + profile ─────────────────────────
        try:
            from context.model_capability import resolve_model_capability
            model_cap = resolve_model_capability(model_id)
            snapshot.context_window = MAX_CONTEXT_TOKENS
        except Exception:
            model_cap = None
            logger.debug(f"Could not resolve model capability for {model_id}")

        try:
            from context.context_profile import get_profile, scale_profile_for_model

            profile = get_profile(profile_name)
            if model_cap:
                profile = scale_profile_for_model(profile, model_cap)

            snapshot.max_input_tokens = MAX_CONTEXT_TOKENS
            snapshot.output_reserved = 0
            snapshot.safety_margin = 0
            snapshot.available_budget = MAX_CONTEXT_TOKENS
        except Exception as e:
            logger.warning(f"Could not resolve profile: {e}")

        # ── Query real counts from DB ──────────────────────────────────
        await self._query_counts(conv_uuid, db, snapshot)

        # ── Compute token estimates from real data ─────────────────────
        snapshot.message_tokens = await self._estimate_message_tokens(
            conv_uuid, db
        )
        snapshot.tool_result_tokens = await self._estimate_tool_result_tokens(
            conv_uuid, db
        )
        snapshot.system_prompt_tokens = 1200  # Base system prompt

        # Current query (last user message)
        current_query_tokens = await self._estimate_current_query_tokens(conv_uuid, db)

        # Total estimate
        snapshot.total_estimated_tokens = (
            snapshot.system_prompt_tokens
            + snapshot.message_tokens
            + snapshot.tool_result_tokens
            + current_query_tokens
        )

        # Compute usage ratio
        if snapshot.available_budget > 0:
            snapshot.usage_ratio = min(
                1.0,
                snapshot.total_estimated_tokens / snapshot.available_budget,
            )
        else:
            snapshot.usage_ratio = 0.0

        # Compression level from ratio
        snapshot.compression_level = "none"
        snapshot.budget_healthy = snapshot.usage_ratio < 1.0

        # Component breakdown
        snapshot.components = {
            "system_prompt": snapshot.system_prompt_tokens,
            "recent_messages": snapshot.message_tokens,
            "tool_results": snapshot.tool_result_tokens,
            "current_query": current_query_tokens,
        }

        logger.debug(
            "Context snapshot built",
            extra={
                "conversation_id": conversation_id,
                "total_tokens": snapshot.total_estimated_tokens,
                "usage_ratio": round(snapshot.usage_ratio, 3),
                "messages": snapshot.message_count,
                "tool_calls": snapshot.tool_call_count,
            },
        )

        return snapshot

    # ===================================================================
    # DB queries
    # ===================================================================

    async def _query_counts(
        self,
        conv_uuid: uuid.UUID,
        db: AsyncSession,
        snapshot: ContextSnapshot,
    ) -> None:
        """Query all counts from the database in one batch."""
        from db.models import (
            ConversationMemory,
            Message,
            ToolCall,
            WorkspaceFile,
        )

        # Message count (only user + assistant)
        msg_q = select(func.count()).select_from(Message).where(
            Message.conversation_id == conv_uuid,
            Message.role.in_(["user", "assistant"]),
        )
        msg_result = await db.execute(msg_q)
        snapshot.message_count = msg_result.scalar() or 0

        # User message count (conversation rounds)
        user_q = select(func.count()).select_from(Message).where(
            Message.conversation_id == conv_uuid,
            Message.role == "user",
        )
        user_result = await db.execute(user_q)
        snapshot.user_message_count = user_result.scalar() or 0

        # Tool call count
        tool_q = select(func.count()).select_from(ToolCall).where(
            ToolCall.conversation_id == conv_uuid
        )
        tool_result = await db.execute(tool_q)
        snapshot.tool_call_count = tool_result.scalar() or 0

        # Workspace file count
        file_q = select(func.count()).select_from(WorkspaceFile).where(
            WorkspaceFile.conversation_id == conv_uuid
        )
        file_result = await db.execute(file_q)
        snapshot.workspace_file_count = file_result.scalar() or 0

        # Memory item count
        mem_q = select(func.count()).select_from(ConversationMemory).where(
            ConversationMemory.conversation_id == conv_uuid,
            ConversationMemory.is_active == True,
        )
        mem_result = await db.execute(mem_q)
        snapshot.memory_item_count = mem_result.scalar() or 0

    async def _estimate_message_tokens(
        self,
        conv_uuid: uuid.UUID,
        db: AsyncSession,
    ) -> int:
        """Estimate total tokens in conversation messages.

        Uses the content field (which is content-blocks JSON) to
        compute a rough character-based token estimate.
        """
        from db.models import Message

        # Get message content summaries (not full content to avoid large payloads)
        q = (
            select(Message.content, Message.thinking_content)
            .where(
                Message.conversation_id == conv_uuid,
                Message.role.in_(["user", "assistant"]),
            )
            .order_by(Message.created_at.desc())
        )
        result = await db.execute(q)
        rows = result.all()

        total = 0
        assistant_thinking_kept = 0
        for content, thinking in rows:
            total += estimate_content_tokens(content)
            if thinking and assistant_thinking_kept < 5:
                total += estimate_tokens(str(thinking))
                assistant_thinking_kept += 1

        return total

    async def _estimate_tool_result_tokens(
        self,
        conv_uuid: uuid.UUID,
        db: AsyncSession,
    ) -> int:
        """Estimate total tokens in tool call results."""
        from db.models import ToolCall

        q = (
            select(ToolCall.id, ToolCall.tool_name, ToolCall.result)
            .where(
                ToolCall.conversation_id == conv_uuid,
                ToolCall.status.in_(["completed", "failed"]),
            )
            .order_by(ToolCall.created_at.desc())
        )
        result = await db.execute(q)
        rows = result.all()

        total = 0
        for result_id, tool_name, res in rows:
            if res is None:
                continue
            content = format_tool_result_for_context(
                res,
                conversation_id=str(conv_uuid),
                tool_name=str(tool_name),
                tool_result_id=str(result_id),
            )
            total += estimate_tokens(content)

        return total

    async def _estimate_current_query_tokens(
        self,
        conv_uuid: uuid.UUID,
        db: AsyncSession,
    ) -> int:
        """Estimate tokens in the most recent user message."""
        from db.models import Message

        q = (
            select(Message.content)
            .where(
                Message.conversation_id == conv_uuid,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .limit(1)
        )
        result = await db.execute(q)
        row = result.scalar_one_or_none()
        if row is None:
            return 0
        return estimate_content_tokens(row)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_tracker: ContextTracker | None = None


def get_context_tracker() -> ContextTracker:
    """Get the global ContextTracker singleton."""
    global _tracker
    if _tracker is None:
        _tracker = ContextTracker()
    return _tracker
