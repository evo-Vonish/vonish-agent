#!/usr/bin/env python3
"""Demo: Echo Tool for Agent Loop testing.

This demonstrates the full tool call -> execute -> result -> model loop.

Usage:
    # Add backend to Python path, then run:
    PYTHONPATH=/path/to/project/backend python examples/echo_tool_demo.py
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """Standard result wrapper for skill execution."""
    success: bool
    result: Any
    metadata: dict = field(default_factory=dict)


class BaseSkill:
    """Abstract base class for all skills/tools."""

    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)

    async def execute(self, **kwargs) -> SkillResult:
        raise NotImplementedError


class EchoTool(BaseSkill):
    """A simple echo tool for testing the Agent Loop.

    Demonstrates:
    - Skill registration
    - Parameter validation
    - Result formatting
    - Metadata collection
    """

    name = "echo"
    description = "Echo back the input message"
    parameters = {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Message to echo"},
            "prefix": {"type": "string", "description": "Optional prefix", "default": ""},
        },
        "required": ["message"],
    }

    async def execute(self, message: str, prefix: str = "") -> SkillResult:
        """Execute the echo tool.

        Args:
            message: Message to echo back
            prefix: Optional prefix to prepend

        Returns:
            SkillResult with the echoed message
        """
        output = f"{prefix}{message}" if prefix else f"Echo: {message}"
        return SkillResult(
            success=True,
            result=output,
            metadata={
                "tool": "echo",
                "input_length": len(message),
                "has_prefix": bool(prefix),
            },
        )


async def demo() -> None:
    """Run the echo tool demo."""
    print("=" * 60)
    print("Echo Tool Demo")
    print("=" * 60)

    tool = EchoTool()

    # Demo 1: Basic echo
    print("\n1. Basic echo:")
    result = await tool.execute(message="Hello, Agent!")
    print(f"   Result: {result.result}")
    print(f"   Metadata: {result.metadata}")

    # Demo 2: Echo with prefix
    print("\n2. Echo with prefix:")
    result = await tool.execute(message="Important!", prefix="[ALERT] ")
    print(f"   Result: {result.result}")
    print(f"   Metadata: {result.metadata}")

    # Demo 3: Echo JSON schema
    print("\n3. Tool schema (for model function calling):")
    import json

    schema = {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }
    print(f"   {json.dumps(schema, indent=2, ensure_ascii=False)}")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
