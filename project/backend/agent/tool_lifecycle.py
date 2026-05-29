"""Tool Result Lifecycle for the Agent system.

Implements a five-level lifecycle for tool results:
1. Raw - Original output
2. Filtered - Security/environment filtering
3. Formatted - Structured formatting
4. Compressed - Size reduction
5. Final - Ready for context injection
"""

from __future__ import annotations

import json
from pydantic import BaseModel, Field
from typing import Any, Awaitable, Callable

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class ToolResultLifecycle(BaseModel):
    """Represents a tool result at each lifecycle stage."""

    tool_name: str
    call_id: str
    raw: Any = None
    filtered: Any = None
    formatted: Any = None
    compressed: Any = None
    final: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    def is_successful(self) -> bool:
        """Check if the lifecycle completed successfully."""
        return self.final is not None and len(self.errors) == 0

    def to_dict(self) -> dict[str, Any]:
        """Convert lifecycle to dictionary for logging/debugging."""
        return {
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "has_raw": self.raw is not None,
            "has_filtered": self.filtered is not None,
            "has_formatted": self.formatted is not None,
            "has_compressed": self.compressed is not None,
            "has_final": self.final is not None,
            "errors": self.errors,
        }


# ---------------------------------------------------------------------------
# Lifecycle Processor
# ---------------------------------------------------------------------------


class ToolLifecycleProcessor(BaseModel):
    """Processes tool results through a five-level lifecycle.

    Level 1 - Raw: Original tool output
    Level 2 - Filtered: Remove sensitive/env-specific data
    Level 3 - Formatted: Convert to structured format
    Level 4 - Compressed: Reduce size for context
    Level 5 - Final: Ready for model context injection
    """

    def __init__(self) -> None:
        self._filters: list[Callable[[Any], Any]] = []
        self._formatters: dict[str, Callable[[Any], Any]] = {}
        self._compressors: list[Callable[[Any, int], Any]] = []
        self._max_final_size: int = 4000  # characters

    # ------------------------------------------------------------------
    # Level 1: Raw
    # ------------------------------------------------------------------

    async def process_raw(
        self, tool_name: str, call_id: str, raw_result: Any
    ) -> ToolResultLifecycle:
        """Start lifecycle processing with raw result.

        Args:
            tool_name: Name of the tool.
            call_id: Tool call ID.
            raw_result: Original tool output.

        Returns:
            ToolResultLifecycle with all stages processed.
        """
        lifecycle = ToolResultLifecycle(
            tool_name=tool_name,
            call_id=call_id,
            raw=raw_result,
        )

        try:
            # Level 2: Filter
            lifecycle.filtered = self._apply_filter(raw_result)

            # Level 3: Format
            lifecycle.formatted = self._apply_format(tool_name, lifecycle.filtered)

            # Level 4: Compress
            lifecycle.compressed = self._apply_compress(
                lifecycle.formatted, self._max_final_size
            )

            # Level 5: Final
            lifecycle.final = self._apply_final(lifecycle.compressed)

        except Exception as e:
            logger.error(
                f"Tool lifecycle processing error: {tool_name}",
                extra={"error": str(e), "call_id": call_id},
            )
            lifecycle.errors.append(f"Lifecycle processing failed: {e}")
            # Fallback: use raw as final
            lifecycle.final = self._fallback_final(raw_result)

        return lifecycle

    # ------------------------------------------------------------------
    # Level 2: Filter
    # ------------------------------------------------------------------

    def _apply_filter(self, raw: Any) -> Any:
        """Apply security and environment filtering.

        Removes sensitive information like:
        - API keys and tokens
        - File system absolute paths
        - Environment variables with secrets
        """
        if isinstance(raw, str):
            return self._filter_string(raw)
        elif isinstance(raw, dict):
            return {k: self._apply_filter(v) for k, v in raw.items()}
        elif isinstance(raw, list):
            return [self._apply_filter(item) for item in raw]
        return raw

    def _filter_string(self, text: str) -> str:
        """Filter sensitive patterns from string."""
        import re

        # Remove API keys
        patterns = [
            (r'sk-[a-zA-Z0-9]{20,}', 'sk-***'),
            (r'[a-f0-9]{32,}', '***'),
            (r'password[=:]\s*\S+', 'password=***'),
            (r'token[=:]\s*\S+', 'token=***'),
        ]
        result = text
        for pattern, replacement in patterns:
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result

    # ------------------------------------------------------------------
    # Level 3: Format
    # ------------------------------------------------------------------

    def _apply_format(self, tool_name: str, data: Any) -> Any:
        """Format the filtered result into structured form."""
        # Tool-specific formatters
        formatter = self._formatters.get(tool_name)
        if formatter:
            return formatter(data)

        # Default: convert to structured dict
        if isinstance(data, str):
            # Try to detect if it's structured content
            if len(data) > 1000:
                return {
                    "type": "text",
                    "content": data[:1000],
                    "truncated": True,
                    "original_length": len(data),
                }
            return {"type": "text", "content": data}

        return data

    # ------------------------------------------------------------------
    # Level 4: Compress
    # ------------------------------------------------------------------

    def _apply_compress(self, data: Any, max_size: int) -> Any:
        """Compress formatted result to fit context budget.

        Args:
            data: Formatted data.
            max_size: Maximum size in characters.
        """
        serialized = json.dumps(data, ensure_ascii=False, default=str)

        if len(serialized) <= max_size:
            return data

        # Compression strategies based on data type
        if isinstance(data, dict):
            return self._compress_dict(data, max_size)
        elif isinstance(data, str):
            return data[:max_size] + "... [truncated]"

        return data

    def _compress_dict(self, data: dict[str, Any], max_size: int) -> dict[str, Any]:
        """Compress a dictionary to fit size budget."""
        # Strategy: Summarize large text fields
        result = {}
        current_size = 2  # {}

        for key, value in data.items():
            if isinstance(value, str) and len(value) > 500:
                # Truncate long text
                truncated = value[:500] + "... [truncated]"
                entry = {key: truncated}
            else:
                entry = {key: value}

            entry_size = len(json.dumps(entry, ensure_ascii=False, default=str))
            if current_size + entry_size < max_size:
                result[key] = value if not isinstance(value, str) or len(value) <= 500 else value[:500] + "... [truncated]"
                current_size += entry_size
            else:
                result["_truncated"] = True
                break

        return result

    # ------------------------------------------------------------------
    # Level 5: Final
    # ------------------------------------------------------------------

    def _apply_final(self, data: Any) -> dict[str, Any]:
        """Prepare the final result for context injection.

        Returns a standardized dict that the context builder can consume.
        """
        if isinstance(data, dict):
            return {
                "tool_result": True,
                "data": data,
                "format": "structured",
            }

        return {
            "tool_result": True,
            "data": str(data),
            "format": "text",
        }

    def _fallback_final(self, raw: Any) -> dict[str, Any]:
        """Create a minimal final result from raw output."""
        return {
            "tool_result": True,
            "data": str(raw)[:2000],
            "format": "text",
            "_fallback": True,
        }

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_formatter(
        self, tool_name: str, formatter: Callable[[Any], Any]
    ) -> None:
        """Register a custom formatter for a tool."""
        self._formatters[tool_name] = formatter

    def set_max_final_size(self, size: int) -> None:
        """Set the maximum final result size."""
        self._max_final_size = size


# ---------------------------------------------------------------------------
# Global Instance
# ---------------------------------------------------------------------------

_lifecycle_processor: ToolLifecycleProcessor | None = None


def get_lifecycle_processor() -> ToolLifecycleProcessor:
    """Get the global lifecycle processor."""
    global _lifecycle_processor
    if _lifecycle_processor is None:
        _lifecycle_processor = ToolLifecycleProcessor()
    return _lifecycle_processor
