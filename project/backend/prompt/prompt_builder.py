"""Prompt Builder — assembles system prompt from blocks."""
from __future__ import annotations

from prompt.prompt_blocks import (
    PromptBlock,
    BuiltPrompt,
    FIXED_HEADER,
    BEHAVIOR_RULES,
    WORKSPACE_RULES,
    TOOL_INTRO,
    FIXED_FOOTER,
)
from prompt.tool_prompt_registry import ToolPromptRegistry


class PromptBuilder:
    """Builds the system prompt as an ordered list of blocks.

    Fixed blocks are always included. Tool blocks are injected only
    for enabled tools, ordered by priority then tool name.
    """

    def __init__(self) -> None:
        self._tool_registry = ToolPromptRegistry()

    def build(
        self,
        enabled_tools: list[str],
        model_id: str = "",
    ) -> BuiltPrompt:
        """Assemble the final system prompt.

        Args:
            enabled_tools: List of tool names currently enabled.
            model_id: Optional model hint (reserved for future use).

        Returns:
            BuiltPrompt with assembled content, blocks, and metadata.
        """
        # Collect blocks
        blocks: list[PromptBlock] = [
            FIXED_HEADER,
            BEHAVIOR_RULES,
            WORKSPACE_RULES,
        ]

        # Tool blocks (only for enabled tools)
        if enabled_tools:
            blocks.append(TOOL_INTRO)
            tool_blocks = self._tool_registry.get_enabled_tool_blocks(enabled_tools)
            # Sort: by priority, then by id
            tool_blocks.sort(key=lambda b: (b.priority, b.id))
            blocks.extend(tool_blocks)

        blocks.append(FIXED_FOOTER)

        # Assemble content
        content = "\n\n".join(b.content for b in blocks if b.enabled)

        # Estimate tokens: ~4 chars per token
        token_estimate = len(content) // 4

        result = BuiltPrompt(
            content=content,
            blocks=blocks,
            token_estimate=token_estimate,
            enabled_tools=sorted(enabled_tools),
        )
        result.compute_hash()
        return result

    def preview(
        self,
        enabled_tools: list[str],
        model_id: str = "",
    ) -> BuiltPrompt:
        """Same as build() but with verbose metadata for the preview API."""
        return self.build(enabled_tools=enabled_tools, model_id=model_id)
