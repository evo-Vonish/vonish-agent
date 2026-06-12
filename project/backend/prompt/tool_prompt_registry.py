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
                "- On Windows, use PowerShell syntax such as Get-ChildItem; do not use Unix-only commands like ls -la or Bash brace expansion.\n"
                "- A failed command is a normal tool result. Read stderr/hint, change strategy, and continue instead of treating it as workflow failure.\n"
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
        "open_artifact": {
            "intro": (
                "## Tool: open_artifact\n"
                "Open a generated or modified workspace file in the user's right-side Workbench preview/editor.\n"
                "Use after creating deliverables such as reports, PDFs, PPTX, DOCX, XLSX, HTML pages, images, or code files.\n"
                "This is a handoff tool: it lets the user inspect the artifact, select text/elements/pages/ranges, quote them into the composer, and request targeted edits.\n"
                "Call it with the relative workspace path after the file exists; then briefly tell the user what was opened.\n"
                "If it reports missing file, do not retry the same path blindly. List the output directory, resolve the actual path/name, then open the existing artifact.\n"
            ),
        },
        "list_artifact_skills": {
            "intro": (
                "## Tool: list_artifact_skills\n"
                "List bundled artifact-production skills for polished deliverables.\n"
                "Use when planning DOCX, XLSX, PDF, or PPTX work and you need to confirm available skill files.\n"
            ),
        },
        "read_artifact_skill": {
            "intro": (
                "## Tool: read_artifact_skill\n"
                "Read the bundled artifact-production skill instructions for DOCX, XLSX, PDF, or PPTX.\n"
                "Mandatory before creating or heavily editing polished deliverables in those formats.\n"
                "Choose the skill matching the target output: docx, xlsx, pdf, or pptx.\n"
                "Default files include SKILL.md, procedure.yaml, validators.yaml, and design_tokens.yaml; include_shared also loads Artifact Plan, Priority System, Visual Review, and Context Recall guidance.\n"
                "After reading, follow the skill's procedure graph, P0/P1 gates, visual review, and recall checkpoints. If a referenced CLI or route file is missing, adapt using available tools and clearly avoid pretending it ran.\n"
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
                "If downstream fetch/extract fails repeatedly, stop retrying the same query path and summarize available successful evidence.\n"
            ),
        },
        "research_fetch": {
            "intro": (
                "## Tool: research_fetch\n"
                "Fetch one URL through Research Core. It returns summary + content_ref + content_hash, not full page text.\n"
                "Use content_ref as evidence reference; do not ask for full page text unless required.\n"
                "Empty text, 403/404/timeout, or extraction failure is normal web noise. Do not retry the same domain more than once; skip it and use another source.\n"
            ),
        },
        "deep_research": {
            "intro": (
                "## Tool: deep_research\n"
                "Run the full research pipeline: search, crawl, dedupe, evidence pack, and compact source refs.\n"
                "Use for current events, broad research questions, or when citations/evidence are needed.\n"
                "Results are budget-protected: use evidence_pack and content_refs rather than full page bodies.\n"
                "If this tool returns a degraded/skipped or HTTP error result, do not loop through research_fetch/web_fetch repeatedly. Use partial sources, state limitations, or ask the user.\n"
            ),
        },
        "research_status": {
            "intro": (
                "## Tool: research_status\n"
                "Check Research Core service and pipeline health before diagnosing web research failures. The status includes service_alive, search_ok, fetch_ok, extract_ok, and result_store_ok.\n"
            ),
        },
        "git_status": {
            "intro": (
                "## Tool: git_status\n"
                "Inspect the current workspace Git status.\n"
                "Use before summarizing changes, reviewing modifications, or checking whether files are dirty.\n"
                "This is read-only and workspace-bound. Do not use shell git commit/reset/restore for version management.\n"
            ),
        },
        "git_diff": {
            "intro": (
                "## Tool: git_diff\n"
                "Read workspace Git diffs for working tree, staged changes, a single file, or a commit.\n"
                "Use when the user asks what changed, before reporting completed edits, and before commit-style summaries.\n"
                "This is read-only and workspace-bound. Do not use it to mutate repository state.\n"
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
        "git_checkpoint": {
            "intro": (
                "## Tool: git_checkpoint\n"
                "Create an explicit checkpoint in VonishAgent's hidden Shadow Git timeline. This never commits to the user's real .git repository.\n"
                "Allowed kinds: agent_milestone, artifact_version, handoff_checkpoint.\n"
                "Use agent_milestone after meaningful multi-file progress, artifact_version after producing an important file version, and handoff_checkpoint before a handoff summary.\n"
                "Do not call it for every small edit. Do not use system_auto, crash_checkpoint, rollback_restore, or user_milestone; those are runtime-only.\n"
            ),
        },
        "expand_tool_result": {
            "intro": (
                "## Tool: expand_tool_result\n"
                "Tool results are normally shown as bounded head + key sections + tail views while their complete content remains stored.\n"
                "Call this read-only tool only when one complete stored result is required.\n"
                "Prefer tool_result_id/content_ref/result_ref from the truncation marker or research result; tool_name selects the latest matching result.\n"
                "Use builds to control how many upcoming context builds keep the selected result fully visible.\n"
            ),
        },
        "CRAZY_for_tool_results": {
            "intro": (
                "## Tool: CRAZY_for_tool_results\n"
                "Temporarily expand ALL stored tool results into context. This is intentionally expensive.\n"
                "Use before final report synthesis, after completing research/search/fetch phases, when auditing all evidence, or when debugging a complex chain where many prior outputs matter.\n"
                "Do not use early in a task. Prefer focus_tool_results when only specific evidence is needed.\n"
                "Set builds to the smallest useful value. When the window expires, call it again only if full recall is still necessary.\n"
            ),
        },
        "focus_tool_results": {
            "intro": (
                "## Tool: focus_tool_results\n"
                "Temporarily expand selected stored tool results by tool_result_ids, tool_names, query/grep text, status, and latest count.\n"
                "Use when writing a summary from selected research pages, revisiting command output, comparing failed tool calls, or recalling specific files/search results.\n"
                "This is the preferred recall tool for normal work because it preserves context while exposing the relevant complete details.\n"
            ),
        },
        "context_map": {
            "intro": (
                "## Tool: context_map\n"
                "Shows the recallable memory map without expanding raw content.\n"
                "Use this before broad recall to inspect available user constraints, pinned items, chat messages, tool results, and recall ids.\n"
                "Do not call MAX recall blindly when context_map can identify a small target.\n"
            ),
        },
        "custom_context_recall": {
            "intro": (
                "## Tool: custom_context_recall\n"
                "Recall exact or structured stored context by target list: tool_result, chat_message, file, file_range, grep, search_result, browser_snapshot, shell_output, diff, user_constraint, plan, or artifact_validation.\n"
                "Returned content is also injected into active_recalled_context for the requested turns, so later model rounds can keep using it without guessing.\n"
                "Use raw mode only when exact text is necessary. Prefer summary_plus_segments or key_segments for normal work.\n"
                "Mandatory before editing code from compressed file views, writing final reports from compressed evidence, citing facts, or debugging complex errors.\n"
            ),
        },
        "recall_maximum": {
            "intro": (
                "## Tool: recall_maximum\n"
                "Activates MAX recall mode for a short window and rebuilds a broad active_recalled_context block according to scope, priority, query, and token budget.\n"
                "It includes constraints, plans, recent chat, and selected tool evidence; tool outputs may also be temporarily expanded.\n"
                "Use only for final synthesis, broad evidence audits, large refactors, or complex debugging after context_map is insufficient.\n"
                "Always provide a reason and use the smallest useful turns value.\n"
            ),
        },
        "pin_memory": {
            "intro": (
                "## Tool: pin_memory\n"
                "Pin a user constraint, active file, locked decision, unresolved error, plan, or note so it remains visible in context memory.\n"
                "Use when the user gives a hard requirement, corrects a prior mistake, names a critical path, or says to remember something.\n"
            ),
        },
        "unpin_memory": {
            "intro": (
                "## Tool: unpin_memory\n"
                "Deactivate a pinned memory item by pin id when it is no longer relevant or has been superseded.\n"
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
