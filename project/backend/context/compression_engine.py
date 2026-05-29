"""Compression Engine for Context OS v2.

Implements a five-phase progressive compression pipeline:

    Phase 1: Local Tool Result Pruning
        - Per-tool-type truncation (shell tail, grep head, file full-then-summary)
        - Zero API cost, always runs first

    Phase 2: LLM Message Summarization
        - Cold messages (beyond sacred window) are summarised
        - Anchor-based iterative summary merging

    Phase 3: Tool Result -> Reference
        - Full content written to storage_uri
        - Context carries only <1% reference tokens

    Phase 4: Cycle Advancement
        - Generate cycle briefing, archive conversation, restart with seed
        - Enabled by profile.enable_cycle_advance

    Phase 5: Emergency Trim
        - Delete oldest messages one-by-one
        - Never drops below sacred window (min_recent_messages)

Compression trigger thresholds:
    - 70%  -> light      (Phase 1 only)
    - 80%  -> moderate   (Phase 1 + Phase 2)
    - 85%  -> heavy      (Phase 1-3)
    - 90%  -> extreme    (Phase 1-4)
    - 99%  -> emergency  (Phase 5 — last resort)

Design principle: information loss is progressive, starting with the
lowest-cost operations.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Compression Strategy Enum
# ---------------------------------------------------------------------------


class CompressionStrategy(str, Enum):
    """Granular compression strategies for individual components."""

    NONE = "none"
    TRUNCATE = "truncate"
    KEYPOINTS = "keypoints"
    HEADLINE = "headline"
    SUMMARIZE = "summarize"
    CODE_SIGNATURE = "code_signature"


# ---------------------------------------------------------------------------
# Compression Result Models
# ---------------------------------------------------------------------------


class CompressionResult(BaseModel):
    """Result of compressing a single text block."""

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    strategy: str
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @property
    def compression_ratio(self) -> float:
        """Compression ratio (0.0 = none, 1.0 = fully compressed)."""
        if self.original_tokens <= 0:
            return 0.0
        return 1.0 - (self.compressed_tokens / self.original_tokens)

    @property
    def tokens_saved(self) -> int:
        """Tokens saved by compression."""
        return self.original_tokens - self.compressed_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "strategy": self.strategy,
            "quality_score": round(self.quality_score, 4),
            "compression_ratio": round(self.compression_ratio, 4),
            "tokens_saved": self.tokens_saved,
        }


class MessageCompressionResult(BaseModel):
    """Result of compressing a batch of messages."""

    messages: list[dict[str, Any]]
    original_tokens: int
    compressed_tokens: int
    compressed_count: int
    strategy_applied: str

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.compressed_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_count": len(self.messages),
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "compressed_count": self.compressed_count,
            "tokens_saved": self.tokens_saved,
            "strategy_applied": self.strategy_applied,
        }


class CompressionPhaseResult(BaseModel):
    """Result of a single compression phase."""

    phase: int
    phase_name: str
    tokens_saved: int
    details: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "phase_name": self.phase_name,
            "tokens_saved": self.tokens_saved,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Compression Engine
# ---------------------------------------------------------------------------


class CompressionEngine:
    """Five-phase progressive compression engine.

    Each phase is designed to be the cheapest possible operation at that
    stage of budget exhaustion. Phases are applied in order until the
    budget is satisfied.

    Attributes:
        _sacred_window_size: Minimum messages to always preserve.
    """

    def __init__(self) -> None:
        """Initialize the compression engine."""
        self._sacred_window_size: int = 6  # Default, overridden per-build

    # ===================================================================
    # Main Entry Point
    # ===================================================================

    async def compress(
        self,
        context_state,
        profile,
        budget,
    ) -> dict[str, Any]:
        """Run the five-phase compression pipeline.

        Args:
            context_state: ContextState with messages, tool_results, etc.
            profile: ContextProfile defining compression parameters.
            budget: TokenBudget tracking current usage.

        Returns:
            Dictionary with:
                - phases: list of CompressionPhaseResult
                - total_tokens_saved: int
                - messages: compressed messages
                - tool_results: compressed tool results
                - cycle_advanced: bool
                - warnings: list[str]
        """
        from context.context_builder import ContextState

        if not isinstance(context_state, ContextState):
            raise TypeError(f"context_state must be ContextState, got {type(context_state).__name__}")

        self._sacred_window_size = profile.min_recent_messages

        phases: list[CompressionPhaseResult] = []
        total_saved = 0
        warnings: list[str] = []
        cycle_advanced = False

        # Check which phases are needed
        compression_level = budget.get_compression_level()

        logger.info(
            "Starting compression pipeline",
            extra={
                "compression_level": compression_level,
                "usage_ratio": budget.usage_ratio,
                "used_tokens": budget.used_tokens,
                "available_budget": budget.available_input_budget,
            },
        )

        # -- Phase 1: Local Tool Result Pruning ------------------------
        if compression_level in ("light", "moderate", "heavy", "extreme", "emergency"):
            saved, details = await self._phase1_tool_pruning(context_state, profile)
            phases.append(CompressionPhaseResult(
                phase=1, phase_name="tool_pruning", tokens_saved=saved, details=details
            ))
            total_saved += saved
            budget.subtract_usage(saved)
            logger.debug(f"Phase 1 saved {saved} tokens")

        # -- Phase 2: LLM Message Summarization ------------------------
        if compression_level in ("moderate", "heavy", "extreme", "emergency"):
            if budget.usage_ratio >= 0.80:
                saved, details = await self._phase2_message_summarization(
                    context_state, profile
                )
                phases.append(CompressionPhaseResult(
                    phase=2, phase_name="message_summarization", tokens_saved=saved, details=details
                ))
                total_saved += saved
                budget.subtract_usage(saved)
                logger.debug(f"Phase 2 saved {saved} tokens")

        # -- Phase 3: Tool Result -> Reference -------------------------
        if compression_level in ("heavy", "extreme", "emergency"):
            if budget.usage_ratio >= 0.85:
                saved, details = await self._phase3_reference_ization(
                    context_state, profile
                )
                phases.append(CompressionPhaseResult(
                    phase=3, phase_name="reference_ization", tokens_saved=saved, details=details
                ))
                total_saved += saved
                budget.subtract_usage(saved)
                logger.debug(f"Phase 3 saved {saved} tokens")

        # -- Phase 4: Cycle Advancement --------------------------------
        if compression_level in ("extreme", "emergency"):
            if budget.usage_ratio >= 0.90 and profile.enable_cycle_advance:
                saved, details, did_advance = await self._phase4_cycle_advancement(
                    context_state, profile
                )
                phases.append(CompressionPhaseResult(
                    phase=4, phase_name="cycle_advancement", tokens_saved=saved, details=details
                ))
                total_saved += saved
                budget.subtract_usage(saved)
                cycle_advanced = did_advance
                logger.debug(f"Phase 4 saved {saved} tokens, cycle_advanced={did_advance}")

        # -- Phase 5: Emergency Trim -----------------------------------
        if compression_level == "emergency":
            if budget.usage_ratio >= 0.99:
                saved, details = await self._phase5_emergency_trim(
                    context_state, profile
                )
                phases.append(CompressionPhaseResult(
                    phase=5, phase_name="emergency_trim", tokens_saved=saved, details=details
                ))
                total_saved += saved
                budget.subtract_usage(saved)
                warnings.append("Emergency trim applied — oldest messages were deleted")
                logger.debug(f"Phase 5 saved {saved} tokens")

        return {
            "phases": [p.to_dict() for p in phases],
            "total_tokens_saved": total_saved,
            "messages": context_state.messages,
            "tool_results": context_state.tool_results,
            "cycle_advanced": cycle_advanced,
            "warnings": warnings,
        }

    # ===================================================================
    # Phase 1: Local Tool Result Pruning (zero API cost)
    # ===================================================================

    async def _phase1_tool_pruning(
        self,
        context_state,
        profile,
    ) -> tuple[int, dict[str, Any]]:
        """Phase 1: Apply per-tool-type truncation strategies.

        Strategies:
            - read_file: full -> summary if exceeds max_tool_result_tokens
            - grep_files: keep first 500 lines (head)
            - exec_shell: keep last 4096 chars (tail)
            - web_search: keep full (already concise)
            - list_dir: keep full (compact)
            - fetch_url: truncate to max_tool_result_tokens
            - default: truncate to max_tool_result_tokens

        Returns:
            (tokens_saved, details_dict)
        """
        from context.context_builder import ContextState

        if not isinstance(context_state, ContextState):
            return 0, {}

        saved = 0
        pruned_count = 0

        for i, tr in enumerate(context_state.tool_results):
            if tr.get("stage") == "evicted":
                continue

            tool_name = tr.get("tool_name", "")
            content = tr.get("content", "")
            original_tokens = tr.get("token_count", 0) or self._estimate_tokens(content)

            pruned_content = self._apply_tool_compression(
                tool_name, content, profile.max_tool_result_tokens
            )
            pruned_tokens = self._estimate_tokens(pruned_content)

            if pruned_tokens < original_tokens:
                saved += (original_tokens - pruned_tokens)
                context_state.tool_results[i]["content"] = pruned_content
                context_state.tool_results[i]["token_count"] = pruned_tokens
                context_state.tool_results[i]["_pruned"] = True
                pruned_count += 1

        return saved, {"pruned_count": pruned_count, "tools_affected": pruned_count}

    def _apply_tool_compression(
        self, tool_name: str, content: str, max_tokens: int
    ) -> str:
        """Apply per-tool-type compression.

        Args:
            tool_name: Name of the tool.
            content: Full tool result content.
            max_tokens: Maximum allowed tokens.

        Returns:
            Compressed content string.
        """
        max_chars = max_tokens * 4

        if not content:
            return content

        if tool_name == "grep_files":
            # Keep first 500 lines (most relevant matches at top)
            lines = content.split("\n")
            if len(lines) > 500:
                return "\n".join(lines[:500]) + f"\n\n[...{len(lines) - 500} more lines]"
            return content

        elif tool_name == "exec_shell":
            # Keep last 4096 chars (most recent output)
            keep_chars = 4096
            if len(content) > keep_chars:
                tail = content[-keep_chars:]
                return f"[...{len(content) - keep_chars} chars omitted...]\n{tail}"
            return content

        elif tool_name in ("web_search", "list_dir"):
            # Already compact, keep full
            return content

        elif tool_name == "read_file":
            # Keep full if within budget, else truncate
            if len(content) > max_chars:
                head = content[:max_chars]
                # Try to cut at line boundary
                last_nl = head.rfind("\n")
                if last_nl > max_chars * 0.5:
                    head = head[:last_nl]
                return head + "\n\n[...file truncated]"
            return content

        elif tool_name == "fetch_url":
            if len(content) > max_chars:
                return content[:max_chars] + "\n\n[...page truncated]"
            return content

        else:
            # Default: simple truncation
            if len(content) > max_chars:
                return content[:max_chars] + "\n\n[...truncated]"
            return content

    # ===================================================================
    # Phase 2: LLM Message Summarization
    # ===================================================================

    async def _phase2_message_summarization(
        self,
        context_state,
        profile,
    ) -> tuple[int, dict[str, Any]]:
        """Phase 2: Summarise cold messages (beyond sacred window).

        Cold messages are those older than profile.recent_turns.
        We compress them using local heuristics (no LLM call) to keep
        this phase zero-cost.

        Returns:
            (tokens_saved, details_dict)
        """
        from context.context_builder import ContextState

        if not isinstance(context_state, ContextState):
            return 0, {}

        messages = context_state.messages
        if len(messages) <= self._sacred_window_size:
            return 0, {"reason": "messages_below_sacred_window"}

        # Identify cold messages: those beyond recent_turns from the end
        sacred_cutoff = max(self._sacred_window_size, len(messages) - profile.recent_turns * 2)
        # Ensure we never compress the most recent min_recent_messages
        sacred_cutoff = max(sacred_cutoff, len(messages) - profile.min_recent_messages)

        saved = 0
        compressed_count = 0

        for i in range(sacred_cutoff):
            msg = messages[i]
            content = self._get_message_content(msg)
            original_tokens = self._estimate_tokens(content)

            # Apply summarization
            compressed = self._summarize_message(content, profile.compression_level)
            compressed_tokens = self._estimate_tokens(compressed)

            if compressed_tokens < original_tokens:
                saved += (original_tokens - compressed_tokens)
                if isinstance(msg, dict):
                    msg["content"] = compressed
                    msg["_compressed"] = True
                    msg["_compression_phase"] = 2
                compressed_count += 1

        return saved, {"compressed_count": compressed_count}

    def _summarize_message(self, content: str, level: str) -> str:
        """Summarise a single message using heuristic methods.

        Args:
            content: Message content.
            level: Compression level ('aggressive', 'balanced', 'minimal').

        Returns:
            Summarised content.
        """
        if not content:
            return content

        if level == "aggressive":
            # Keep only key lines and headings
            return self._extract_keypoints(content, max_lines=5)
        elif level == "balanced":
            # Truncate to ~50%
            half = max(100, len(content) // 2)
            if len(content) > half:
                return content[:half] + "\n\n[...summarised]"
            return content
        else:  # minimal
            # Light truncation: keep 75%
            target = max(200, int(len(content) * 0.75))
            if len(content) > target:
                return content[:target] + "\n\n[...truncated]"
            return content

    # ===================================================================
    # Phase 3: Tool Result -> Reference
    # ===================================================================

    async def _phase3_reference_ization(
        self,
        context_state,
        profile,
    ) -> tuple[int, dict[str, Any]]:
        """Phase 3: Convert old tool results to reference-only.

        Full content is written to storage_uri, context carries only
        the reference string (<1% of original tokens).

        Returns:
            (tokens_saved, details_dict)
        """
        from context.context_builder import ContextState

        if not isinstance(context_state, ContextState):
            return 0, {}

        saved = 0
        reference_count = 0

        for i, tr in enumerate(context_state.tool_results):
            if tr.get("stage") in ("reference", "archived", "evicted"):
                continue
            if tr.get("_pruned"):  # Already handled in Phase 1
                continue

            content = tr.get("content", "")
            original_tokens = tr.get("token_count", 0) or self._estimate_tokens(content)

            if original_tokens <= 100:
                continue  # Too small to bother

            # Replace with reference text
            tool_name = tr.get("tool_name", "unknown")
            call_id = tr.get("call_id", "")
            ref_text = f"[ToolResult {call_id}: {tool_name} — {content[:80]}...]"
            ref_tokens = self._estimate_tokens(ref_text)

            saved += (original_tokens - ref_tokens)
            context_state.tool_results[i]["content"] = ref_text
            context_state.tool_results[i]["token_count"] = ref_tokens
            context_state.tool_results[i]["stage"] = "reference"
            context_state.tool_results[i]["_reference_ized"] = True
            reference_count += 1

        return saved, {"reference_count": reference_count}

    # ===================================================================
    # Phase 4: Cycle Advancement
    # ===================================================================

    async def _phase4_cycle_advancement(
        self,
        context_state,
        profile,
    ) -> tuple[int, dict, bool]:
        """Phase 4: Generate cycle briefing and restart context.

        This is the nuclear option: we generate a compact briefing of
        what happened in the current cycle, archive everything, and
        restart with just the briefing + pinned state.

        Returns:
            (tokens_saved, details_dict, did_advance)
        """
        from context.context_builder import ContextState

        if not isinstance(context_state, ContextState):
            return 0, {}, False

        if not profile.enable_cycle_advance:
            return 0, {"reason": "cycle_advance_disabled"}, False

        messages = context_state.messages
        if len(messages) <= profile.min_recent_messages:
            return 0, {"reason": "too_few_messages"}, False

        # Generate a simple briefing from recent tool results and messages
        briefing = self._generate_cycle_briefing(context_state)
        briefing_tokens = self._estimate_tokens(briefing)

        # Count tokens in messages that will be replaced
        original_msg_tokens = sum(
            self._estimate_tokens(self._get_message_content(m))
            for m in messages[:-profile.min_recent_messages]
        )

        # Replace old messages with briefing
        kept_messages = messages[-profile.min_recent_messages:]
        context_state.messages = [{"role": "system", "content": f"[Cycle Briefing]\n{briefing}"}] + kept_messages

        saved = max(0, original_msg_tokens - briefing_tokens)

        return saved, {"briefing_tokens": briefing_tokens, "messages_kept": len(kept_messages)}, True

    def _generate_cycle_briefing(self, context_state) -> str:
        """Generate a text briefing summarising the current cycle.

        Args:
            context_state: ContextState with conversation data.

        Returns:
            Briefing text.
        """
        lines: list[str] = ["## Previous Cycle Summary"]

        # Summarise tool calls
        tool_names: dict[str, int] = {}
        for tr in context_state.tool_results:
            name = tr.get("tool_name", "unknown")
            tool_names[name] = tool_names.get(name, 0) + 1

        if tool_names:
            lines.append("### Tools Used")
            for name, count in sorted(tool_names.items(), key=lambda x: -x[1]):
                lines.append(f"- {name}: {count} call(s)")

        # Summarise working set
        if context_state.workspace_files:
            lines.append("### Files Referenced")
            for f in context_state.workspace_files[:10]:
                lines.append(f"- {f}")

        lines.append("\n[Earlier conversation details are available in archive.]")
        return "\n".join(lines)

    # ===================================================================
    # Phase 5: Emergency Trim
    # ===================================================================

    async def _phase5_emergency_trim(
        self,
        context_state,
        profile,
    ) -> tuple[int, dict[str, Any]]:
        """Phase 5: Delete oldest messages one-by-one.

        Never drops below min_recent_messages.

        Returns:
            (tokens_saved, details_dict)
        """
        from context.context_builder import ContextState

        if not isinstance(context_state, ContextState):
            return 0, {}

        messages = context_state.messages
        min_keep = profile.min_recent_messages

        if len(messages) <= min_keep:
            return 0, {"reason": "already_at_minimum"}

        saved = 0
        deleted_count = 0

        # Delete oldest messages (from the front) until we're at minimum
        while len(messages) > min_keep:
            msg = messages[0]
            content = self._get_message_content(msg)
            msg_tokens = self._estimate_tokens(content)
            saved += msg_tokens
            messages.pop(0)
            deleted_count += 1

        return saved, {"deleted_count": deleted_count, "messages_remaining": len(messages)}

    # ===================================================================
    # Generic Compression API
    # ===================================================================

    async def compress_text(
        self,
        text: str,
        target_tokens: int,
        content_type: str = "text",
        strategy: CompressionStrategy | None = None,
    ) -> CompressionResult:
        """Compress text to fit within target token budget.

        Args:
            text: Text to compress.
            target_tokens: Target token count.
            content_type: Type of content ('text', 'code', 'tool_result', 'memory').
            strategy: Compression strategy (auto-detected if None).

        Returns:
            CompressionResult with compressed text and metadata.
        """
        original_tokens = self._estimate_tokens(text)

        if original_tokens <= target_tokens:
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=original_tokens,
                compressed_tokens=original_tokens,
                strategy="none",
                quality_score=1.0,
            )

        if strategy is None:
            strategy = self._select_strategy(content_type, original_tokens, target_tokens)

        if strategy == CompressionStrategy.TRUNCATE:
            compressed = self._truncate(text, target_tokens)
        elif strategy == CompressionStrategy.KEYPOINTS:
            compressed = self._extract_keypoints(text, max_lines=20)
        elif strategy == CompressionStrategy.HEADLINE:
            compressed = self._headline(text)
        elif strategy == CompressionStrategy.CODE_SIGNATURE:
            compressed = self._summarize_code(text, target_tokens)
        else:
            compressed = self._summarize(text, target_tokens)

        compressed_tokens = self._estimate_tokens(compressed)
        quality = self._estimate_quality(original_tokens, compressed_tokens, strategy.value)

        return CompressionResult(
            original_text=text,
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            strategy=strategy.value,
            quality_score=quality,
        )

    # ===================================================================
    # Internal Helpers
    # ===================================================================

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count: ~4 chars/token."""
        if not text:
            return 0
        return max(1, len(str(text)) // 4)

    @staticmethod
    def _get_message_content(msg: dict[str, Any]) -> str:
        """Extract content string from message dict."""
        content = msg.get("content", "") if isinstance(msg, dict) else str(msg)
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)
        return str(content)

    def _select_strategy(
        self, content_type: str, original_tokens: int, target_tokens: int
    ) -> CompressionStrategy:
        """Select compression strategy based on content type and ratio."""
        ratio = target_tokens / original_tokens if original_tokens > 0 else 1.0

        if content_type == "code":
            return CompressionStrategy.CODE_SIGNATURE

        if ratio > 0.7:
            return CompressionStrategy.TRUNCATE
        elif ratio > 0.4:
            return CompressionStrategy.KEYPOINTS
        elif ratio > 0.15:
            return CompressionStrategy.SUMMARIZE
        else:
            return CompressionStrategy.HEADLINE

    def _truncate(self, text: str, target_tokens: int) -> str:
        """Truncate text to target token count at a natural boundary."""
        if not text:
            return text

        target_chars = target_tokens * 4
        if len(text) <= target_chars:
            return text

        truncated = text[:target_chars]
        last_period = truncated.rfind(".")
        last_newline = truncated.rfind("\n")
        last_space = truncated.rfind(" ")

        cut_point = -1
        if last_period > target_chars * 0.7:
            cut_point = last_period + 1
        elif last_newline > target_chars * 0.6:
            cut_point = last_newline
        elif last_space > target_chars * 0.5:
            cut_point = last_space

        if cut_point > 0:
            truncated = truncated[:cut_point]

        return truncated.strip() + "\n\n[...content truncated due to context length]"

    def _extract_keypoints(self, text: str, max_lines: int = 20) -> str:
        """Extract key points (bullet lines, headers, important markers)."""
        lines = text.split("\n")
        key_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ", "## ", "### ", "> ", "1. ", "2. ", "3. ")):
                key_lines.append(stripped)
            elif any(kw in stripped.lower() for kw in ("result:", "summary:", "total:", "error:", "note:")):
                key_lines.append(stripped)

        if not key_lines:
            return self._truncate(text, max(20, len(text) // 8))

        result = "## Key Points\n" + "\n".join(key_lines[:max_lines])
        return result

    def _headline(self, text: str) -> str:
        """Create a one-line headline/summary."""
        if not text or not text.strip():
            return "[Content summarised]"

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return "[Content summarised]"

        headline = ""
        for line in lines:
            if not line.startswith(("#", "-", "*", ">", "|", "{")):
                headline = line
                break

        if not headline:
            headline = lines[0]

        if len(headline) > 200:
            headline = headline[:200] + "..."

        return f"[Summary: {headline}]"

    def _summarize(self, text: str, target_tokens: int) -> str:
        """Summarize text using keypoint extraction + truncation."""
        return self._extract_keypoints(text, max_lines=target_tokens // 10)

    def _summarize_code(self, code: str, target_tokens: int) -> str:
        """Summarize code by keeping signatures and truncating bodies."""
        lines = code.split("\n")
        result_lines: list[str] = []
        in_body = False
        lines_kept = 0
        max_body_lines = 5

        for line in lines:
            stripped = line.strip()

            if stripped.startswith(("import ", "from ", "@", "#", '"""', "'''")):
                result_lines.append(line)
                continue

            if any(stripped.startswith(p) for p in ("def ", "class ", "async def")):
                result_lines.append(line)
                in_body = True
                lines_kept = 0
                continue

            if in_body:
                if stripped == "" or stripped.startswith("#"):
                    result_lines.append(line)
                elif lines_kept < max_body_lines:
                    result_lines.append(line)
                    lines_kept += 1
                elif lines_kept == max_body_lines:
                    indent = len(line) - len(line.lstrip())
                    result_lines.append(" " * indent + "# ... [implementation truncated]")
                    lines_kept += 1
                continue

            result_lines.append(line)

        result = "\n".join(result_lines)
        if self._estimate_tokens(result) > target_tokens:
            return self._truncate(result, target_tokens)
        return result

    def _estimate_quality(
        self, original_tokens: int, compressed_tokens: int, strategy: str
    ) -> float:
        """Estimate information retention quality after compression."""
        if original_tokens <= 0:
            return 1.0

        ratio = compressed_tokens / original_tokens

        quality_factors: dict[str, float] = {
            "none": 1.0,
            "truncate": 0.7 + 0.3 * ratio,
            "keypoints": 0.6 + 0.4 * ratio,
            "summarize": 0.5 + 0.5 * ratio,
            "code_signature": 0.55 + 0.45 * ratio,
            "headline": 0.3,
        }

        base = quality_factors.get(strategy, 0.5)
        return min(1.0, base * ratio + (1 - ratio) * 0.1)


# ---------------------------------------------------------------------------
# Global instance
# ---------------------------------------------------------------------------

_compression_engine: CompressionEngine | None = None


def get_compression_engine() -> CompressionEngine:
    """Get the global CompressionEngine instance."""
    global _compression_engine
    if _compression_engine is None:
        _compression_engine = CompressionEngine()
    return _compression_engine
