"""Prompt Block — typed, sortable, hashable prompt fragments."""
from __future__ import annotations

import hashlib
from pydantic import BaseModel, Field


class PromptBlock(BaseModel):
    """A single unit of prompt content.

    Blocks are assembled in priority order (lower = first), then by id.
    """

    id: str
    type: str
    enabled: bool = True
    priority: int = 100
    content: str
    source: str = "system"


class BuiltPrompt(BaseModel):
    """The final assembled prompt with metadata."""

    content: str
    blocks: list[PromptBlock]
    token_estimate: int
    enabled_tools: list[str] = Field(default_factory=list)
    hash: str = ""

    def compute_hash(self) -> str:
        self.hash = hashlib.sha256(
            self.content.encode("utf-8")
        ).hexdigest()[:16]
        return self.hash


# ── Block Types (priority defines order) ─────────────────────────────────

BLOCK_TYPE_PRIORITY: dict[str, int] = {
    "fixed_header":     0,
    "model_identity":   10,
    "behavior_rules":   20,
    "workspace_rules":  30,
    "tool_intro":       40,
    "tool_definition":  50,
    "tool_usage_rule":  60,
    "fixed_footer":     90,
}


# ── Fixed Blocks (always enabled) ────────────────────────────────────────

FIXED_HEADER = PromptBlock(
    id="fixed_header",
    type="fixed_header",
    priority=BLOCK_TYPE_PRIORITY["fixed_header"],
    enabled=True,
    source="system",
    content=(
        "You are an AI assistant in the VonishAgent workbench. "
        "Tools are available via function calling — call them directly. "
        "NEVER output <tool_calls>, <invoke>, or <parameter> XML in text. "
        "After using a tool, respond conversationally.\n"
    ),
)

BEHAVIOR_RULES = PromptBlock(
    id="behavior_rules",
    type="behavior_rules",
    priority=BLOCK_TYPE_PRIORITY["behavior_rules"],
    enabled=True,
    source="system",
    content=(
        "Behavior rules:\n"
        "- Use tools when they help answer the user's question.\n"
        "- After using a tool, synthesize results into a clear natural-language response.\n"
        "- If a tool fails, explain the error and suggest alternatives.\n"
        "- Do not claim access to tools that are not listed below.\n"
        "- Do not fabricate tool results.\n"
    ),
)

WORKSPACE_RULES = PromptBlock(
    id="workspace_rules",
    type="workspace_rules",
    priority=BLOCK_TYPE_PRIORITY["workspace_rules"],
    enabled=True,
    source="system",
    content=(
        "Workspace rules:\n"
        "- All file paths are relative to the current conversation workspace.\n"
        "- Create output files in outputs/ directory.\n"
        "- Do not modify files outside the workspace.\n"
    ),
)

TOOL_INTRO = PromptBlock(
    id="tool_intro",
    type="tool_intro",
    priority=BLOCK_TYPE_PRIORITY["tool_intro"],
    enabled=True,
    source="system",
    content=(
        "Available tools (only those listed below are accessible):\n"
    ),
)

FIXED_FOOTER = PromptBlock(
    id="fixed_footer",
    type="fixed_footer",
    priority=BLOCK_TYPE_PRIORITY["fixed_footer"],
    enabled=True,
    source="system",
    content=(
        "Remember:\n"
        "- Only use tools that are explicitly listed above.\n"
        "- If you need a disabled tool, tell the user to enable it in the Tool Management panel.\n"
        "- All file operations go through enabled workspace tools.\n"
    ),
)
