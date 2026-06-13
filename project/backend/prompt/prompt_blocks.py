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

TODO_RULES = PromptBlock(
    id="todo_rules",
    type="behavior_rules",
    priority=BLOCK_TYPE_PRIORITY["behavior_rules"],
    enabled=True,
    source="system",
    content=(
        "Todo rules (critical):\n"
        "- For complex multi-step tasks, call set_todo_list(mode='replace') at the start.\n"
        "- Update todo items as you complete each step: set_todo_list(mode='update').\n"
        "- Mark the currently-in-progress item as 'doing', completed ones as 'done'.\n"
        "- Before giving a final summary, ensure ALL todo items are 'done' or 'cancelled'.\n"
        "- NEVER announce a task as finished if its todo item is still 'todo' or 'doing'.\n"
        "- If blocked by missing info, mark item 'blocked' and call ask_user_question.\n"
        "- To create directories, use create_directories instead of shell mkdir for cross-platform safety.\n"
        "- Avoid Bash brace expansion {a,b} on Windows. Use create_directories or Python pathlib.\n"
    ),
)

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
        "ALWAYS format responses in Markdown: use ## headings, **bold**, "
        "`code`, - lists, and > quotes. Code blocks must use ``` with language tag. "
        "After using a tool, respond conversationally with Markdown.\n"
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
        "- Before creating or substantially editing polished deliverables (.docx, .xlsx, .pdf), call read_artifact_skill for the matching format and follow its procedure, validation gates, visual review, and recall checkpoints.\n"
        "- Use list_artifact_skills if you are unsure which artifact skills are bundled.\n"
        "- To create slide decks / presentations (.pptx), you MUST use generate_presentation (the PPT Artifact Engine), NOT hand-written python-pptx in ipython. Call list_presentation_options first to choose a theme and per-slide layouts, then pass only content. The engine owns geometry, colour, fonts, and runs validation + auto-repair before delivery. If the returned validation report says deliverable=false, tell the user which slides failed and offer to regenerate — never present a blocked deck as finished.\n"
        "- When the user selects/references a slide ELEMENT in the Workbench and asks to change just that element (reword a title, recolour a shape, move/resize), use patch_presentation with the deck's deck_path, the slide_index, and operations targeting the element_id — do NOT regenerate the whole deck for a local edit.\n"
        "- To undo deck edits / go back to an earlier state, use revert_presentation with the deck_path and a version_id from the deck's versions list (shown in the manifest). Each generate/patch is a saved version; a revert is itself versioned so you can roll forward again.\n"
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
        "- For change review, pre-commit checks, or modification summaries, prefer git_status and git_diff before reading files manually.\n"
        "- Use git_history when the user asks who changed code, when it changed, or when blame/log context is needed.\n"
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
