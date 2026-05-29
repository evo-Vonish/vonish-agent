"""Tool Call Parser for the Agent system.

Parses JSON Output tool calls from model responses.
Supports multiple tool calls (calls array).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from core.errors import ToolError
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class ParsedToolCall(BaseModel):
    """A single parsed tool call."""

    tool: str
    arguments: dict[str, Any]
    call_id: str = ""


class ParseResult(BaseModel):
    """Result of parsing tool calls from model output."""

    has_tool_calls: bool
    calls: list[ParsedToolCall] = Field(default_factory=list)
    raw_text: str = ""
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Tool Call Parser
# ---------------------------------------------------------------------------


class ToolCallParser:
    """Parse tool calls from model JSON output.

    Expected format (SPEC.md Section 9):
    {
        "type": "tool_calls",
        "calls": [
            {"tool": "read_file", "arguments": {"path": "..."}},
            {"tool": "web_search", "arguments": {"query": "..."}}
        ]
    }

    Also supports parsing JSON embedded in markdown code blocks.
    """

    MAX_TOOL_CALLS_PER_STEP: int = 4  # balanced profile default

    def __init__(self, max_calls_per_step: int | None = None) -> None:
        self.max_calls = max_calls_per_step or self.MAX_TOOL_CALLS_PER_STEP

    def parse(self, text: str) -> ParseResult:
        """Parse tool calls from model output text.

        Handles:
        - Pure JSON output
        - JSON in markdown code blocks (```json ... ```)
        - Multiple tool calls in calls array

        Args:
            text: Raw model output text.

        Returns:
            ParseResult with extracted tool calls.
        """
        raw_text = text.strip()

        if not raw_text:
            return ParseResult(has_tool_calls=False, raw_text=raw_text)

        # Try to extract JSON from markdown code block
        json_text = self._extract_json_from_markdown(raw_text)

        if not json_text:
            # Not a tool call - regular text
            return ParseResult(has_tool_calls=False, raw_text=raw_text)

        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return ParseResult(
                has_tool_calls=False,
                raw_text=raw_text,
                errors=[f"Invalid JSON: {e}"],
            )

        # Check if it's a tool_calls structure
        if data.get("type") == "tool_calls":
            return self._parse_tool_calls(data, raw_text)

        # Check if it has a calls field directly
        if "calls" in data and isinstance(data["calls"], list):
            return self._parse_tool_calls(
                {"type": "tool_calls", "calls": data["calls"]}, raw_text
            )

        # Single tool call format: {"tool": "...", "arguments": {...}}
        if "tool" in data and "arguments" in data:
            return self._parse_tool_calls(
                {"type": "tool_calls", "calls": [data]}, raw_text
            )

        return ParseResult(has_tool_calls=False, raw_text=raw_text)

    def _extract_json_from_markdown(self, text: str) -> str | None:
        """Extract JSON from markdown code block or raw text (even with surrounding text)."""
        # Try markdown code block
        pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1).strip()

        text = text.strip()

        # Try pure JSON
        if text.startswith("{") and text.endswith("}"):
            return text

        # Try to find a JSON object embedded in surrounding text
        # Match { ... }  with balanced braces
        return self._find_json_in_mixed_text(text)

    def _find_json_in_mixed_text(self, text: str) -> str | None:
        """Find the first complete JSON object in text that may have extra content."""
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escaped = False
        for i in range(start, len(text)):
            ch = text[i]

            if escaped:
                escaped = False
                continue

            if ch == "\\" and in_string:
                escaped = True
                continue

            if ch == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    def _parse_tool_calls(self, data: dict[str, Any], raw_text: str) -> ParseResult:
        """Parse the tool_calls structure."""
        calls_raw = data.get("calls", [])
        calls: list[ParsedToolCall] = []
        errors: list[str] = []

        if len(calls_raw) > self.max_calls:
            errors.append(
                f"Too many tool calls: {len(calls_raw)} > max {self.max_calls}"
            )
            calls_raw = calls_raw[: self.max_calls]

        for i, call_data in enumerate(calls_raw):
            call_id = f"call_{i}_{hash(json.dumps(call_data, sort_keys=True)) & 0xFFFFFF:06x}"

            tool_name = call_data.get("tool", "")
            arguments = call_data.get("arguments", {})

            if not tool_name:
                errors.append(f"Tool call {i}: missing 'tool' field")
                continue

            if not isinstance(arguments, dict):
                errors.append(
                    f"Tool call {i}: 'arguments' must be an object, got {type(arguments).__name__}"
                )
                # Try to normalize
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                else:
                    arguments = {}

            # Validate tool exists
            from agent.tool_registry import ToolRegistry

            registry = ToolRegistry()
            if registry.get(tool_name) is None:
                errors.append(f"Tool call {i}: unknown tool '{tool_name}'")
                continue

            # Validate arguments
            validation = registry.validate_call(tool_name, arguments)
            if not validation.valid:
                errors.extend(
                    [f"Tool call {i} ({tool_name}): {e}" for e in validation.errors]
                )
                arguments = validation.normalized_arguments

            calls.append(
                ParsedToolCall(
                    tool=tool_name,
                    arguments=arguments,
                    call_id=call_id,
                )
            )

        return ParseResult(
            has_tool_calls=len(calls) > 0,
            calls=calls,
            raw_text=raw_text,
            errors=errors,
        )

    def validate_single_call(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Validate a single tool call.

        Args:
            tool_name: Name of the tool.
            arguments: Arguments to validate.

        Returns:
            Tuple of (is_valid, error_messages).
        """
        from agent.tool_registry import ToolRegistry

        registry = ToolRegistry()
        tool_def = registry.get(tool_name)

        if tool_def is None:
            return False, [f"Unknown tool: {tool_name}"]

        result = registry.validate_call(tool_name, arguments)
        return result.valid, result.errors
