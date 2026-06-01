"""Tool Prompt Registry — maps enabled tools to PromptBlocks."""
from __future__ import annotations

from prompt.prompt_blocks import PromptBlock, BLOCK_TYPE_PRIORITY


class ToolPromptRegistry:
    """Registry that generates prompt blocks for enabled tools."""

    TOOL_PROMPTS: dict[str, dict] = {
        "read_file": {
            "intro": (
                "## Tool: read_file\n"
                "Read a file from the current workspace.\n"
                "Rules:\n"
                "- Only reads files within the workspace.\n"
                "- Large files should be read in chunks with offset/limit.\n"
                "- Do not guess file contents — always call this tool.\n"
            ),
        },
        "edit_file": {
            "intro": (
                "## Tool: edit_file\n"
                "Apply search/replace edits to a workspace file.\n"
                "Rules:\n"
                "- old_string must match exactly (including whitespace).\n"
                "- Single file, single edit per call.\n"
                "- Works within workspace boundaries only.\n"
            ),
        },
        "shell_command": {
            "intro": (
                "## Tool: shell_command\n"
                "Execute a shell command in the workspace.\n"
                "Rules:\n"
                "- Commands run in the conversation workspace directory.\n"
                "- Output is truncated (stdout/stderr limit).\n"
                "- Avoid destructive commands. Use with caution.\n"
            ),
        },
        "ipython": {
            "intro": (
                "## Tool: ipython\n"
                "Execute Python code in a persistent IPython kernel bound to the workspace.\n"
                "Session modes: continue (default, variables persist), new, reset, ephemeral.\n"
                "Rules:\n"
                "- Variable state persists across calls in continue mode.\n"
                "- Use outputs/ directory for generated files.\n"
                "- Matplotlib charts are saved to outputs/.\n"
                "- Do not use subprocess or network calls (sandboxed).\n"
            ),
        },
        "web_fetch": {
            "intro": (
                "## Tool: web_fetch\n"
                "Deep-fetch and analyze a web page.\n"
                "Extracts: main content (text/markdown), frontend source (buttons, forms, "
                "interactive elements), page resources.\n"
                "Modes: auto (default), static (HTTP), dynamic (browser render for SPA).\n"
            ),
        },
        "web_search": {
            "intro": (
                "## Tool: web_search\n"
                "Deprecated compatibility wrapper. Prefer research_search.\n"
            ),
        },
        "research_search": {
            "intro": (
                "## Tool: research_search\n"
                "Use for web search. It routes intent, searches multiple engines, cleans URLs, ranks quality, and deduplicates.\n"
                "Returns compact snippets only. Follow with research_fetch for specific pages or deep_research for full research.\n"
            ),
        },
        "research_fetch": {
            "intro": (
                "## Tool: research_fetch\n"
                "Fetch one URL through Research Core. It returns summary + content_ref + content_hash, not full page text.\n"
                "Use content_ref as evidence reference; do not ask for full page text unless required.\n"
            ),
        },
        "deep_research": {
            "intro": (
                "## Tool: deep_research\n"
                "Run the full research pipeline: search, crawl, dedupe, evidence pack, and compact source refs.\n"
                "Use for current events, broad research questions, or when citations/evidence are needed.\n"
                "Results are budget-protected: use evidence_pack and content_refs rather than full page bodies.\n"
            ),
        },
        "research_status": {
            "intro": (
                "## Tool: research_status\n"
                "Check whether the local Research Core runtime is healthy before diagnosing web research failures.\n"
            ),
        },
        "git_status": {
            "intro": (
                "## Tool: git_status\n"
                "Inspect the current workspace Git status.\n"
                "Use before summarizing changes, reviewing modifications, or checking whether files are dirty.\n"
                "This is read-only and workspace-bound.\n"
            ),
        },
        "git_diff": {
            "intro": (
                "## Tool: git_diff\n"
                "Read workspace Git diffs for working tree, staged changes, a single file, or a commit.\n"
                "Use when the user asks what changed, before reporting completed edits, and before commit-style summaries.\n"
                "This is read-only and workspace-bound.\n"
            ),
        },
        "git_history": {
            "intro": (
                "## Tool: git_history\n"
                "Read workspace Git log or blame information.\n"
                "Use for history, authorship, regression, or line provenance questions.\n"
                "This is read-only and workspace-bound.\n"
            ),
        },
    }

    def get_enabled_tool_blocks(self, enabled_tools: list[str]) -> list[PromptBlock]:
        """Generate PromptBlocks for the given list of enabled tool names."""
        blocks: list[PromptBlock] = []
        for name in enabled_tools:
            cfg = self.TOOL_PROMPTS.get(name)
            if not cfg:
                continue
            blocks.append(PromptBlock(
                id=f"tool_{name}",
                type="tool_definition",
                priority=BLOCK_TYPE_PRIORITY["tool_definition"],
                enabled=True,
                content=cfg.get("intro", f"Tool: {name}"),
                source="tool_registry",
            ))
        return blocks

    def list_tool_ids(self) -> list[str]:
        """Return all known tool IDs."""
        return list(self.TOOL_PROMPTS.keys())
