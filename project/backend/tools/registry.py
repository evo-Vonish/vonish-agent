"""Tool registry — central catalog for all available tools.

Reference: CodeWhale ToolRegistry (crates/tui/src/tools/registry.rs)
Supports fuzzy name resolution (model hallucination correction), stable sorting,
and schema aggregation for system-prompt injection.
"""

from __future__ import annotations

from typing import Any, Optional

from core.logging import get_logger

from .base import BaseTool

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central registry for tool discovery and dispatch.

    Usage::

        reg = ToolRegistry()
        reg.register(ReadFileTool())
        reg.register(WriteFileTool())
        tool = reg.get("read_file")
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        # Alias map: alias -> canonical name (e.g. "search" -> "grep_search")
        self._aliases: dict[str, str] = {}

    # -- registration -------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance under its canonical ``tool.name``."""
        name = tool.name
        if name in self._tools:
            logger.warning("Tool %r already registered — overwriting", name)
        self._tools[name] = tool
        logger.debug("Registered tool %r", name)

    def register_alias(self, alias: str, canonical: str) -> None:
        """Register an alias that maps *alias* → *canonical* name."""
        self._aliases[alias] = canonical

    def register_all(self, *tools: BaseTool) -> None:
        """Convenience batch-register."""
        for tool in tools:
            self.register(tool)

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> Optional[BaseTool]:
        """Fetch a tool by exact (or aliased) name."""
        # Exact match
        if name in self._tools:
            return self._tools[name]
        # Alias match
        canonical = self._aliases.get(name)
        if canonical and canonical in self._tools:
            return self._tools[canonical]
        return None

    def list_tools(self) -> list[BaseTool]:
        """Return all registered tools (insertion order)."""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """Return all canonical tool names."""
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools or name in self._aliases

    def __len__(self) -> int:
        return len(self._tools)

    # -- schema / OpenAI function aggregation -------------------------------

    def get_schemas(self) -> dict[str, dict[str, Any]]:
        """Map canonical name → JSON Schema for every registered tool."""
        return {name: tool.schema for name, tool in self._tools.items()}

    def to_functions(self) -> list[dict[str, Any]]:
        """Return the OpenAI ChatCompletion ``functions`` list."""
        return [tool.to_function_definition() for tool in self._tools.values()]

    # -- fuzzy name resolution (model hallucination fix) --------------------

    def resolve_name(self, name: str) -> Optional[str]:
        """Resolve a possibly-hallucinated tool name to a canonical one.

        Resolution order:
        1. Exact match.
        2. Alias match.
        3. Case-insensitive + hyphen→underscore normalised match.
        4. Prefix match (both directions).

        Returns ``None`` when no plausible candidate is found.
        """
        # 1. Exact
        if name in self._tools:
            return name

        # 2. Alias
        if name in self._aliases:
            return self._aliases[name]

        # 3. Normalised (e.g. "read-file" → "read_file")
        norm = name.lower().replace("-", "_")
        for canonical in self._tools:
            if canonical.lower() == norm:
                return canonical

        # 4. Underscore-stripped match (e.g. "ReadFile" → "readfile" ↔ "read_file")
        norm_no_us = norm.replace("_", "")
        for canonical in self._tools:
            if canonical.lower().replace("_", "") == norm_no_us:
                return canonical

        # 5. Prefix match
        for canonical in self._tools:
            c_low = canonical.lower()
            if c_low.startswith(norm) or norm.startswith(c_low):
                return canonical

        return None

    # -- stable sorting -----------------------------------------------------

    def get_sorted_tools(self) -> list[BaseTool]:
        """Return tools sorted alphabetically by name.

        Stable sorting guarantees the same tool appears at the same index
        across rebuilds, which helps regression tests and prompt caching.
        """
        return sorted(self._tools.values(), key=lambda t: t.name)

    # -- system-prompt section builder --------------------------------------

    def build_tools_prompt_section(self) -> str:
        """Build a markdown block that describes all tools for injection into
        the system prompt.

        Format (matches CodeWhale)::

            ## Available Tools
            ...

            ### read_file
            Read a UTF-8 file from the workspace. ...
            Schema: { ... }

            ### write_file
            ...
        """
        lines = [
            "## Available Tools",
            "",
            "You have access to the following tools. Use them by calling the tool",
            "with JSON arguments.",
            "",
        ]
        for tool in self.get_sorted_tools():
            lines.append(f"### {tool.name}")
            lines.append(tool.description)
            import json

            lines.append(f"```json\n{json.dumps(tool.schema, indent=2, ensure_ascii=False)}\n```")
            lines.append("")
        return "\n".join(lines)
