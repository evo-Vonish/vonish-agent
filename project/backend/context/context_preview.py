"""Context Preview for Context OS v2.

Generates a structured preview of how the context will be assembled,
including per-block token counts, budget allocation, and warnings.

This module is read-only: it previews the context but never modifies it.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Preview Models
# ---------------------------------------------------------------------------


class PreviewBlock(BaseModel):
    """A single context block in the preview."""

    type: str = Field(
        ...,
        description=(
            "Block type: system_prompt, user_memory, cycle_briefing, "
            "workspace_refs, workspace_chunks, tool_definitions, "
            "tool_results, recent_messages, current_query"
        ),
    )
    tokens: int = Field(..., ge=0, description="Estimated token count for this block")
    description: str = Field(default="", description="Human-readable description")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "tokens": self.tokens,
            "description": self.description,
        }


class ContextPreviewResponse(BaseModel):
    """Response model for context preview API."""

    conversation_id: str
    profile: str
    model: str
    context_window: int
    estimated_input_tokens: int
    output_reserved_tokens: int
    safety_margin_tokens: int
    available_budget: int
    blocks: list[PreviewBlock]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "profile": self.profile,
            "model": self.model,
            "context_window": self.context_window,
            "estimated_input_tokens": self.estimated_input_tokens,
            "output_reserved_tokens": self.output_reserved_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "available_budget": self.available_budget,
            "blocks": [b.to_dict() for b in self.blocks],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Context Preview
# ---------------------------------------------------------------------------


class ContextPreview:
    """Generates a preview of context assembly without mutating state.

    Usage::

        preview = ContextPreview()
        response = await preview.generate_preview(
            conversation_id="conv_123",
            builder=context_builder,
        )
    """

    async def generate_preview(
        self,
        conversation_id: str,
        builder,
        user_query: str = "[preview mode — no query]",
        model_id: str = "deepseek-chat",
        profile_name: str = "balanced",
    ) -> ContextPreviewResponse:
        """Generate a context preview for a conversation.

        This method performs a lightweight preview by running the build
        pipeline but only collecting block metadata, not full content.

        Args:
            conversation_id: Conversation ID.
            builder: ContextBuilder instance.
            user_query: Optional user query for the preview.
            model_id: Model identifier.
            profile_name: Profile name.

        Returns:
            ContextPreviewResponse with block breakdown.
        """
        from context.context_builder import ContextBuilder
        from context.model_capability import resolve_model_capability
        from context.context_profile import get_profile, scale_profile_for_model
        from context.token_budget import calculate_token_budget

        if not isinstance(builder, ContextBuilder):
            raise TypeError(f"builder must be ContextBuilder, got {type(builder).__name__}")

        t_start = time.perf_counter()

        try:
            # Resolve model + profile
            model = resolve_model_capability(model_id)
            profile = get_profile(profile_name)
            scaled_profile = scale_profile_for_model(profile, model)

            # Calculate budget
            budget = calculate_token_budget(scaled_profile, model)

            # Gather block estimates (lightweight, no DB queries)
            blocks = await self._estimate_blocks(
                conversation_id=conversation_id,
                user_query=user_query,
                profile=scaled_profile,
                model=model,
            )

            total_input_tokens = sum(b.tokens for b in blocks)
            warnings: list[str] = []

            # Check if over budget
            if total_input_tokens > budget.available_input_budget:
                warnings.append(
                    f"Estimated input ({total_input_tokens:,}) exceeds "
                    f"available budget ({budget.available_input_budget:,}) — "
                    f"compression will be triggered"
                )

            # Check individual block budgets
            for block in blocks:
                block_budget = budget.get_component_budget(block.type)
                if block_budget > 0 and block.tokens > block_budget:
                    warnings.append(
                        f"{block.type} ({block.tokens:,} tokens) exceeds "
                        f"component budget ({block_budget:,})"
                    )

            t_end = time.perf_counter()

            logger.debug(
                "Context preview generated",
                extra={
                    "conversation_id": conversation_id,
                    "model_id": model_id,
                    "profile": scaled_profile.name,
                    "total_tokens": total_input_tokens,
                    "time_ms": round((t_end - t_start) * 1000, 2),
                },
            )

            return ContextPreviewResponse(
                conversation_id=conversation_id,
                profile=scaled_profile.name,
                model=model_id,
                context_window=model.context_window,
                estimated_input_tokens=total_input_tokens,
                output_reserved_tokens=budget.output_reserved,
                safety_margin_tokens=budget.safety_margin_tokens,
                available_budget=budget.available_input_budget,
                blocks=blocks,
                warnings=warnings,
            )

        except Exception as e:
            logger.error(
                f"Context preview generation failed: {e}",
                extra={"conversation_id": conversation_id},
            )
            # Return a minimal preview with error indication
            return ContextPreviewResponse(
                conversation_id=conversation_id,
                profile=profile_name,
                model=model_id,
                context_window=0,
                estimated_input_tokens=0,
                output_reserved_tokens=0,
                safety_margin_tokens=0,
                available_budget=0,
                blocks=[],
                warnings=[f"Preview generation failed: {e}"],
            )

    async def _estimate_blocks(
        self,
        conversation_id: str,
        user_query: str,
        profile,
        model,
    ) -> list[PreviewBlock]:
        """Estimate token counts for each context block.

        This is a lightweight estimation that does not query the DB.
        In production, it would query actual counts from the DB.

        Args:
            conversation_id: Conversation ID.
            user_query: User query string.
            profile: ContextProfile.
            model: ModelCapability.

        Returns:
            List of PreviewBlock with estimated token counts.
        """
        blocks: list[PreviewBlock] = []

        # 1. System Prompt (~1200 tokens base)
        sys_tokens = 1200
        blocks.append(PreviewBlock(
            type="system_prompt",
            tokens=sys_tokens,
            description="Base prompt + markdown guide + context budget info",
        ))

        # 2. User Memory (~800 tokens)
        mem_tokens = profile.memory_top_k * 80
        blocks.append(PreviewBlock(
            type="user_memory",
            tokens=mem_tokens,
            description=f"User preferences + project context ({profile.memory_top_k} memories)",
        ))

        # 3. Cycle Briefing (~1500 tokens if present)
        blocks.append(PreviewBlock(
            type="cycle_briefing",
            tokens=0,
            description="No active cycle briefing",
        ))

        # 4. Workspace References (~600 tokens)
        ws_tokens = profile.workspace_chunk_top_k * 75
        blocks.append(PreviewBlock(
            type="workspace_refs",
            tokens=ws_tokens,
            description=f"Working set file references",
        ))

        # 5. Workspace Chunks (~3200 tokens)
        chunk_tokens = profile.workspace_chunk_top_k * 400
        blocks.append(PreviewBlock(
            type="workspace_chunks",
            tokens=chunk_tokens,
            description=f"Relevant file chunks ({profile.workspace_chunk_top_k} chunks)",
        ))

        # 6. Tool Definitions (~2400 tokens for ~12 tools)
        tool_tokens = 2400
        blocks.append(PreviewBlock(
            type="tool_definitions",
            tokens=tool_tokens,
            description="Active tool definitions (alphabetically sorted)",
        ))

        # 7. Tool Results (~4500 tokens)
        result_tokens = profile.max_tool_result_tokens
        blocks.append(PreviewBlock(
            type="tool_results",
            tokens=result_tokens,
            description=f"Tool results (mode: {profile.tool_result_mode})",
        ))

        # 8. Recent Messages (~3800 tokens)
        msg_tokens = profile.recent_turns * 250
        blocks.append(PreviewBlock(
            type="recent_messages",
            tokens=msg_tokens,
            description=f"Last {profile.recent_turns} messages (sacred window)",
        ))

        # 9. Current Query
        query_tokens = max(50, len(user_query) // 4)
        blocks.append(PreviewBlock(
            type="current_query",
            tokens=query_tokens,
            description="Current user message",
        ))

        return blocks


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


async def generate_context_preview(
    conversation_id: str,
    model_id: str = "deepseek-chat",
    profile_name: str = "balanced",
) -> ContextPreviewResponse:
    """Generate a context preview without requiring a builder instance.

    Args:
        conversation_id: Conversation ID.
        model_id: Model identifier.
        profile_name: Profile name.

    Returns:
        ContextPreviewResponse.
    """
    from context.context_builder import ContextBuilder

    preview = ContextPreview()
    builder = ContextBuilder()
    return await preview.generate_preview(
        conversation_id=conversation_id,
        builder=builder,
        model_id=model_id,
        profile_name=profile_name,
    )
