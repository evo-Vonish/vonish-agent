"""Context Builder for Context OS v2.

Core assembly logic that constructs the complete LLM context each turn.

Assembly order (fixed):
    1. System Prompt (hash-deduplicated, stable)
    2. User Memory (recall, structured)
    3. Conversation Memory / Cycle Briefing
    4. Workspace File References (resource:// URI)
    5. Tool Definitions (alphabetically sorted)
    6. Recent Messages (Sacred Window — append-only)
    7. Current Query

Immutable message principle:
    - Messages are NEVER modified after creation.
    - We only APPEND new messages to the list.
    - Old messages may be DROPPED (e.g. in cycle advancement),
      but their content is never rewritten in-place.

Cache stability:
    - System Prompt: SHA-256 hash, only updated on real change
    - Tool Definitions: alphabetically sorted, stable positions
    - Messages: append-only, preserving prefix-cache alignment
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# ContextState — internal mutable state passed between build phases
# ---------------------------------------------------------------------------


class ContextState:
    """Mutable internal state for a single context build.

    This is NOT a Pydantic model because it is mutated heavily during
    the build pipeline. It is private to the builder.
    """

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.tool_results: list[dict[str, Any]] = []
        self.workspace_files: list[str] = []
        self.system_prompt_blocks: list[str] = []
        self.user_memory_text: str = ""
        self.cycle_briefing_text: str = ""
        self.workspace_refs_text: str = ""
        self.workspace_status_text: str = ""
        self.tool_defs_text: str = ""
        self.current_query: str = ""
        self.warnings: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_count": len(self.messages),
            "tool_result_count": len(self.tool_results),
            "workspace_file_count": len(self.workspace_files),
            "workspace_status": self.workspace_status_text,
        }


# ---------------------------------------------------------------------------
# BuiltContext — immutable output of the build process
# ---------------------------------------------------------------------------


class BuiltContext(BaseModel):
    """Result of building context for model input.

    This is the **immutable** output of ContextBuilder.build().
    All fields are derived; no mutable references escape.
    """

    messages: list[dict[str, Any]] = Field(
        default_factory=list,
        description="OpenAI-compatible message list (system + history + current query)",
    )
    system_prompt: str = Field(
        default="",
        description="Complete system prompt string",
    )
    system_prompt_hash: str = Field(
        default="",
        description="SHA-256 hash of the system prompt (for cache dedup)",
    )
    token_count: int = Field(
        default=0,
        description="Total estimated input token count",
    )
    components: dict[str, int] = Field(
        default_factory=dict,
        description="Per-component token usage {name: tokens}",
    )
    tools: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Active tool definitions (alphabetically sorted)",
    )
    profile_name: str = Field(default="balanced")
    model_id: str = Field(default="")
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging and API responses."""
        return {
            "message_count": len(self.messages),
            "system_prompt_length": len(self.system_prompt),
            "system_prompt_hash": self.system_prompt_hash,
            "token_count": self.token_count,
            "components": self.components,
            "tool_count": len(self.tools),
            "profile": self.profile_name,
            "model_id": self.model_id,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# ContextBuilder
# ---------------------------------------------------------------------------


class ContextBuilder:
    """Builds the complete model context from multiple sources.

    Implements the Context OS v2 assembly pipeline:
        1. resolve_model_capability(model_id)
        2. select_context_profile(profile_name, model)
        3. scale_profile_for_model(profile, model)   # adaptive scaling
        4. calculate_token_budget(profile, model)    # component budgets
        5. Assemble blocks in fixed order
        6. Budget check -> compression if needed
        7. Return BuiltContext

    Message immutability:
        - We only APPEND to the messages list.
        - We NEVER rewrite existing message content in-place.
    """

    # Component priority for compression decisions (higher = keep longer)
    COMPONENT_PRIORITY: dict[str, int] = {
        "system_prompt": 100,
        "current_query": 95,
        "tool_definitions": 90,
        "recent_messages": 70,
        "user_memory": 60,
        "cycle_briefing": 55,
        "workspace_refs": 50,
        "workspace_chunks": 45,
        "tool_results": 40,
    }

    def __init__(self) -> None:
        """Initialize context builder with sub-components."""
        self._system_prompt_hash: str = ""
        self._cached_system_prompt: str = ""

    # ===================================================================
    # Main Build Method
    # ===================================================================

    async def build(
        self,
        conversation_id: str,
        user_query: str,
        model_id: str,
        profile_name: str = "balanced",
    ) -> BuiltContext:
        """Build complete context for model input.

        Pipeline:
            1. Resolve model capability
            2. Select and scale context profile
            3. Calculate token budget
            4. Build each context block
            5. Check budget, apply compression if needed
            6. Assemble final messages and return BuiltContext

        Args:
            conversation_id: Current conversation ID.
            user_query: User's current message text.
            model_id: Model identifier (e.g. 'deepseek-chat').
            profile_name: Context profile name ('cheap', 'balanced', 'max').

        Returns:
            BuiltContext with assembled messages, system prompt, tools, and metadata.

        Raises:
            ValueError: If conversation_id or model_id is invalid.
        """
        t_start = time.perf_counter()

        if not conversation_id:
            raise ValueError("conversation_id is required")
        if not model_id:
            raise ValueError("model_id is required")

        # Step 1: Resolve model capability
        model = self._resolve_model_capability(model_id)

        # Step 2: Select profile + auto-scale for model
        profile = self._select_profile(profile_name, model)

        # Step 3: Calculate token budget
        from context.token_budget import calculate_token_budget

        budget = calculate_token_budget(profile, model)

        # Step 4: Build context blocks
        ctx = ContextState()
        ctx.current_query = user_query

        # 4a: System Prompt
        system_prompt = self._build_system_prompt(profile, model)
        ctx.system_prompt_blocks = [system_prompt]
        sys_tokens = self._estimate_tokens(system_prompt)
        budget.add_usage(sys_tokens)

        # 4b: User Memory
        user_memory_text = await self._build_user_memory(conversation_id, user_query, profile)
        ctx.user_memory_text = user_memory_text
        mem_tokens = self._estimate_tokens(user_memory_text)
        budget.add_usage(mem_tokens)

        # 4c: Cycle Briefing (if applicable)
        briefing_text = await self._build_cycle_briefing(conversation_id)
        ctx.cycle_briefing_text = briefing_text
        brief_tokens = self._estimate_tokens(briefing_text)
        budget.add_usage(brief_tokens)

        # 4d: Workspace References
        ws_refs_text = await self._build_workspace_refs(conversation_id, profile)
        ctx.workspace_refs_text = ws_refs_text
        ws_tokens = self._estimate_tokens(ws_refs_text)
        budget.add_usage(ws_tokens)

        workspace_status_text = await self._build_workspace_status(conversation_id)
        ctx.workspace_status_text = workspace_status_text
        workspace_status_tokens = self._estimate_tokens(workspace_status_text)
        budget.add_usage(workspace_status_tokens)

        # 4e: Tool Definitions (alphabetically sorted for cache stability)
        tool_defs = self._fetch_tool_definitions()
        tool_defs.sort(key=lambda t: t.get("name", ""))  # Stable alphabetical order
        ctx.tools = tool_defs
        tool_defs_text = self._format_tool_definitions(tool_defs)
        ctx.tool_defs_text = tool_defs_text
        tool_tokens = self._estimate_tokens(tool_defs_text)
        budget.add_usage(tool_tokens)

        # 4f: Recent Messages (Sacred Window — append-only)
        recent_messages = await self._fetch_recent_messages(conversation_id, profile)
        if recent_messages and recent_messages[-1].get("role") == "user":
            # chat_stream stores the user message before AgentLoop starts; the
            # current query is appended separately below, so drop that duplicate.
            if self._get_msg_content(recent_messages[-1]).strip() == user_query.strip():
                recent_messages = recent_messages[:-1]
        ctx.messages = recent_messages
        msg_tokens = sum(
            self._estimate_tokens(self._get_msg_content(m))
            for m in recent_messages
        )
        budget.add_usage(msg_tokens)

        # 4g: Current Query
        query_tokens = self._estimate_tokens(user_query)
        budget.add_usage(query_tokens)

        # Step 5: Budget check & compression
        components: dict[str, int] = {
            "system_prompt": sys_tokens,
            "user_memory": mem_tokens,
            "cycle_briefing": brief_tokens,
            "workspace_refs": ws_tokens,
            "workspace_status": workspace_status_tokens,
            "tool_definitions": tool_tokens,
            "recent_messages": msg_tokens,
            "current_query": query_tokens,
        }

        budget_status = budget.check_budget()
        warnings: list[str] = []

        if budget_status.needs_compression:
            logger.info(
                "Token budget exceeded threshold, applying compression",
                extra={
                    "conversation_id": conversation_id,
                    "usage_ratio": round(budget_status.usage_ratio, 3),
                    "compression_level": budget_status.compression_level,
                    "used_tokens": budget.used_tokens,
                    "available_budget": budget.available_input_budget,
                },
            )

            from context.compression_engine import CompressionEngine

            engine = CompressionEngine()
            compression_result = await engine.compress(ctx, profile, budget)
            warnings.extend(compression_result.get("warnings", []))

            # Update components after compression
            if compression_result.get("cycle_advanced"):
                warnings.append("Cycle advancement applied")

            # Recalculate token counts after compression
            msg_tokens = sum(
                self._estimate_tokens(self._get_msg_content(m))
                for m in ctx.messages
            )
            components["recent_messages"] = msg_tokens
            components["tool_results"] = sum(
                self._estimate_tokens(tr.get("content", ""))
                for tr in ctx.tool_results
            )

        # Step 6: Final assembly
        # System prompt: deduplicate via hash
        full_system = self._assemble_system_prompt(
            base=system_prompt,
            user_memory=user_memory_text,
            cycle_briefing=briefing_text,
            workspace_refs=ws_refs_text,
            workspace_status=workspace_status_text,
        )
        sys_hash = self._compute_hash(full_system)

        # Build final messages list: system prompt + recent messages + current query
        # IMPORTANT: we create NEW message dicts, never mutate the fetched ones
        final_messages: list[dict[str, Any]] = []

        # System prompt as first message
        if full_system:
            final_messages.append({"role": "system", "content": full_system})

        # Append recent messages (immutable, never modified in-place)
        for msg in ctx.messages:
            final_messages.append(dict(msg))  # Shallow copy for safety

        # Append current user query
        final_messages.append({"role": "user", "content": user_query})

        # Recalculate total tokens
        total_tokens = (
            self._estimate_tokens(full_system)
            + components["recent_messages"]
            + components["current_query"]
            + components.get("tool_results", 0)
        )

        # Ensure tools are in stable alphabetical order
        tools_for_model = [{"type": "function", "function": t} for t in ctx.tools]

        t_end = time.perf_counter()
        build_time_ms = (t_end - t_start) * 1000

        metadata = {
            "conversation_id": conversation_id,
            "profile": profile.name,
            "model_id": model_id,
            "context_window": model.context_window,
            "scaled": profile.name != profile_name,  # True if auto-scaling was applied
            "compression_level": budget_status.compression_level,
            "build_time_ms": round(build_time_ms, 2),
            "message_count": len(final_messages),
            "sacred_window_messages": len(ctx.messages),
            "tool_count": len(tools_for_model),
            "usage_ratio": round(budget_status.usage_ratio, 4),
        }

        logger.info(
            "Context built successfully",
            extra={
                "conversation_id": conversation_id,
                "total_tokens": total_tokens,
                "model_id": model_id,
                "profile": profile.name,
                "compression_level": budget_status.compression_level,
                "build_time_ms": round(build_time_ms, 2),
            },
        )

        return BuiltContext(
            messages=final_messages,
            system_prompt=full_system,
            system_prompt_hash=sys_hash,
            token_count=total_tokens,
            components=components,
            tools=tools_for_model,
            profile_name=profile.name,
            model_id=model_id,
            warnings=warnings,
            metadata=metadata,
        )

    # ===================================================================
    # Profile & Model Resolution
    # ===================================================================

    def _resolve_model_capability(self, model_id: str):
        """Resolve model_id to ModelCapability via the global registry."""
        from context.model_capability import resolve_model_capability

        return resolve_model_capability(model_id)

    def _select_profile(self, profile_name: str, model):
        """Select profile and apply model-aware auto-scaling."""
        from context.context_profile import get_profile, scale_profile_for_model

        profile = get_profile(profile_name)
        scaled = scale_profile_for_model(profile, model)
        return scaled

    # ===================================================================
    # System Prompt (hash-deduplicated)
    # ===================================================================

    def _build_system_prompt(self, profile, model) -> str:
        """Build the system prompt block.

        Uses hash deduplication: if the prompt hasn't changed since
        the last build, the cached version is returned.

        Args:
            profile: ContextProfile.
            model: ModelCapability.

        Returns:
            System prompt string.
        """
        try:
            from api.prompt import get_enabled_tools
            from prompt.prompt_builder import PromptBuilder

            prompt = PromptBuilder().build(
                enabled_tools=get_enabled_tools(),
                model_id=model.model_id,
            ).content
        except Exception:
            prompt = (
                "You are an AI assistant with access to tools. "
                "Your goal is to help the user accomplish their tasks efficiently."
            )

        budget_guide = "\n".join(
            [
                "",
                "## Context Budget",
                f"- Profile: {profile.name}",
                f"- Model: {model.model_id} (ctx: {model.context_window:,})",
                f"- Max input tokens: {profile.max_input_tokens:,}",
                f"- Recent turns kept: {profile.recent_turns}",
                f"- Tool result mode: {profile.tool_result_mode}",
                f"- Memory recall: top {profile.memory_top_k}",
            ]
        )
        prompt = f"{prompt}\n{budget_guide}"

        # Hash deduplication
        prompt_hash = self._compute_hash(prompt)
        if prompt_hash == self._system_prompt_hash and self._cached_system_prompt:
            return self._cached_system_prompt

        self._system_prompt_hash = prompt_hash
        self._cached_system_prompt = prompt
        return prompt

    @staticmethod
    def _compute_hash(text: str) -> str:
        """Compute a 16-char SHA-256 hash for cache deduplication."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    # ===================================================================
    # Context Block Builders
    # ===================================================================

    async def _build_user_memory(self, conversation_id: str, query: str, profile) -> str:
        """Build user memory block via MemorySelector.recall().

        Args:
            conversation_id: Conversation ID.
            query: Current user query for relevance.
            profile: ContextProfile with memory_top_k.

        Returns:
            Formatted user memory text for system prompt.
        """
        try:
            from context.memory_selector import get_memory_selector

            selector = get_memory_selector()

            # Get user_id from conversation (simplified — in production, query DB)
            user_id = await self._get_conversation_user_id(conversation_id)
            if not user_id:
                return ""

            result = await selector.recall(
                user_id=user_id,
                query=query,
                profile=profile,
            )

            return result.format_for_context()

        except Exception as e:
            logger.warning(f"User memory recall failed: {e}")
            return ""

    async def _build_cycle_briefing(self, conversation_id: str) -> str:
        """Build cycle briefing if the conversation has advanced cycles.

        Args:
            conversation_id: Conversation ID.

        Returns:
            Briefing text or empty string if no cycle advancement.
        """
        # In production: query DB for cycle state, generate briefing
        # For now: return empty (no cycle advancement by default)
        return ""

    async def _build_workspace_refs(self, conversation_id: str, profile) -> str:
        """Build workspace file references for context injection.

        Args:
            conversation_id: Conversation ID.
            profile: ContextProfile with workspace_chunk_top_k.

        Returns:
            Formatted workspace references text.
        """
        try:
            from context.workspace_context import get_workspace_context

            ws_ctx = get_workspace_context()
            return ws_ctx.build_workspace_refs(conversation_id, profile)

        except Exception as e:
            logger.warning(f"Workspace refs build failed: {e}")
            return ""

    async def _build_workspace_status(self, conversation_id: str) -> str:
        """Build a compact current workspace status block for the system prompt."""
        try:
            from pathlib import Path

            from services.git_service import git_status, workspace_root

            root = workspace_root(conversation_id)
            status = await git_status(conversation_id)
            file_count = 0
            if root.exists():
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    try:
                        rel_parts = path.relative_to(root).parts
                    except ValueError:
                        continue
                    if ".git" in rel_parts or ".workspace" in rel_parts:
                        continue
                    file_count += 1

            dirty_count = sum(
                len(status.get(key, []) or [])
                for key in ("staged", "modified", "untracked", "deleted", "conflicts")
            )
            git_line = "not a git repository"
            if status.get("is_git_repo"):
                branch = status.get("branch") or "HEAD"
                git_line = f"{branch}, {dirty_count} changed" if dirty_count else f"{branch}, clean"

            return "\n".join(
                [
                    "## Current Workspace",
                    f"- Name: {Path(root).name}",
                    f"- Root: {root}",
                    f"- Git: {git_line}",
                    f"- Files: {file_count}",
                    "- File tree is intentionally not included; use workspace tools when file inspection is needed.",
                ]
            )
        except Exception as e:
            logger.debug(f"Workspace status build failed: {e}")
            return ""

    def _fetch_tool_definitions(self) -> list[dict[str, Any]]:
        """Fetch active tool definitions.

        Returns:
            List of tool definition dicts.
        """
        try:
            from api.prompt import get_enabled_tools
            from agent.tool_registry import ToolRegistry

            registry = ToolRegistry()
            if not registry.list_all():
                from agent.tool_registry import register_default_tools

                register_default_tools()
            enabled = set(get_enabled_tools())
            defs = registry.list_for_context()
            return [
                {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters,
                }
                for d in defs
                if d.name in enabled
            ]
        except Exception as e:
            logger.warning(f"Tool definitions fetch failed: {e}")
            return []

    def _format_tool_definitions(self, tool_defs: list[dict[str, Any]]) -> str:
        """Format tool definitions as text for token estimation.

        Args:
            tool_defs: List of tool definition dicts.

        Returns:
            Formatted text.
        """
        if not tool_defs:
            return ""
        lines = ["## Available Tools"]
        for t in tool_defs:
            lines.append(f"- {t.get('name', 'unknown')}: {t.get('description', '')}")
        return "\n".join(lines)

    async def _fetch_recent_messages(self, conversation_id: str, profile) -> list[dict[str, Any]]:
        """Fetch recent messages (Sacred Window) for a conversation.

        These messages are returned as-is and are NEVER modified in-place.
        Only the newest messages beyond the sacred window may be dropped
        during cycle advancement.

        Args:
            conversation_id: Conversation ID.
            profile: ContextProfile with recent_turns and min_recent_messages.

        Returns:
            List of message dicts (immutable — never modify in-place).
        """
        try:
            import uuid as _uuid
            from sqlalchemy import select

            from db.models import Message as MessageModel
            from db.session import get_session_maker

            conv_uuid = _uuid.UUID(conversation_id)
            limit = max(
                int(getattr(profile, "min_recent_messages", 6) or 6),
                int(getattr(profile, "recent_turns", 16) or 16) * 2,
            )
            session_maker = get_session_maker()
            async with session_maker() as db:
                q = (
                    select(MessageModel)
                    .where(MessageModel.conversation_id == conv_uuid)
                    .order_by(MessageModel.created_at.asc())
                )
                rows = list((await db.execute(q)).scalars().all())[-limit:]

            messages: list[dict[str, Any]] = []
            for row in rows:
                if row.role not in {"system", "user", "assistant"}:
                    continue
                content = self._extract_message_text(row.content)
                if not content:
                    continue
                messages.append(
                    {
                        "role": row.role,
                        "content": content,
                    }
                )
            return messages
        except Exception as e:
            logger.warning(f"Recent messages fetch failed: {e}")
            return []

    async def _get_conversation_user_id(self, conversation_id: str) -> str | None:
        """Get the user_id associated with a conversation.

        Args:
            conversation_id: Conversation ID.

        Returns:
            User ID string or None.
        """
        try:
            import uuid as _uuid
            from sqlalchemy import select

            from db.models import Conversation
            from db.session import get_session_maker

            conv_uuid = _uuid.UUID(conversation_id)
            session_maker = get_session_maker()
            async with session_maker() as db:
                q = select(Conversation.user_id).where(Conversation.id == conv_uuid)
                user_id = (await db.execute(q)).scalar()
            return str(user_id) if user_id else None
        except Exception as e:
            logger.debug(f"Conversation user lookup failed: {e}")
            return None

    def _assemble_system_prompt(
        self,
        base: str,
        user_memory: str,
        cycle_briefing: str,
        workspace_refs: str,
        workspace_status: str = "",
    ) -> str:
        """Assemble the complete system prompt from all blocks.

        Args:
            base: Base system prompt.
            user_memory: User memory text.
            cycle_briefing: Cycle briefing text.
            workspace_refs: Workspace references text.

        Returns:
            Complete system prompt string.
        """
        parts = [base]

        if user_memory:
            parts.extend(["", user_memory])

        if cycle_briefing:
            parts.extend(["", cycle_briefing])

        if workspace_refs:
            parts.extend(["", workspace_refs])

        if workspace_status:
            parts.extend(["", workspace_status])

        return "\n".join(parts)

    # ===================================================================
    # Token Estimation
    # ===================================================================

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count: ~4 chars/token.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        if not text:
            return 0
        return max(1, len(str(text)) // 4)

    @staticmethod
    def _get_msg_content(msg: dict[str, Any]) -> str:
        """Extract content string from a message dict.

        Args:
            msg: Message dictionary.

        Returns:
            Content string.
        """
        if not isinstance(msg, dict):
            return str(msg)
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)
        return str(content)

    @staticmethod
    def _extract_message_text(content: list[dict[str, Any]] | str | None) -> str:
        """Extract model-facing text from stored DB content blocks."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return str(content)

        texts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                texts.append(str(block.get("text")))
            elif block.get("type") == "segments" and isinstance(block.get("segments"), list):
                for segment in block["segments"]:
                    if not isinstance(segment, dict):
                        continue
                    if segment.get("type") == "text" and segment.get("content"):
                        texts.append(str(segment.get("content")))
        return "\n".join(text for text in texts if text.strip()).strip()


# ---------------------------------------------------------------------------
# Context Usage helper
# ---------------------------------------------------------------------------


class ContextUsage(BaseModel):
    """Token usage statistics for a conversation."""

    total_tokens: int
    max_tokens: int
    profile: str
    recent_turns: int
    memory_items: int
    workspace_refs: int
    tool_defs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "profile": self.profile,
            "recent_turns": self.recent_turns,
            "memory_items": self.memory_items,
            "workspace_refs": self.workspace_refs,
            "tool_defs": self.tool_defs,
        }


async def get_context_usage(conversation_id: str) -> ContextUsage:
    """Get token usage statistics for a conversation.

    Args:
        conversation_id: Conversation ID.

    Returns:
        ContextUsage with usage breakdown.
    """
    from context.context_profile import get_profile

    # Simplified — in production, query DB for actual counts
    profile = get_profile("balanced")

    return ContextUsage(
        total_tokens=0,
        max_tokens=profile.max_input_tokens,
        profile=profile.name,
        recent_turns=0,
        memory_items=0,
        workspace_refs=0,
        tool_defs=0,
    )
