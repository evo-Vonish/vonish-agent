"""Model Adapter layer for the Agent system.

Provides a unified interface for different LLM providers:
- DeepSeek (V4-Pro, V4-Flash)
- Kimi (K2.6, K2.5)

Implements abstract ModelAdapter with stream_chat() interface.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Literal, TypedDict

import httpx
from pydantic import BaseModel, Field

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Type Definitions
# ---------------------------------------------------------------------------


class TokenUsage(TypedDict, total=False):
    """Token usage statistics."""

    input_tokens: int
    output_tokens: int
    cached_tokens: int
    reasoning_tokens: int


class StreamChunk(TypedDict):
    """A chunk from the model's streaming response."""

    type: Literal[
        "thinking_delta",
        "text_delta",
        "tool_call",
        "usage",
        "done",
    ]
    content: str | dict[str, Any] | None
    usage: TokenUsage | None
    # Accumulated tool calls (non-streaming, assembled)
    tool_calls: list[dict[str, Any]] | None


class ModelCapability(TypedDict):
    """Capabilities of a specific model."""

    provider: str
    model_id: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool
    supports_json_mode: bool
    supports_thinking: bool
    supports_context_cache: bool


class MessageBlock(BaseModel):
    """A message block for model input.

    Supports:
    - Regular text messages: role + content string
    - Tool-call messages: role="assistant", content=None, tool_calls=[...]
    - Tool-result messages: role="tool", content="result", tool_call_id="..."
    """

    role: str  # system | user | assistant | tool
    content: str | list[dict[str, Any]] | None = None
    thinking_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None


class ToolDefinition(BaseModel):
    """Tool definition for model function calling."""

    name: str
    description: str
    parameters: dict[str, Any]


# ---------------------------------------------------------------------------
# Abstract Model Adapter
# ---------------------------------------------------------------------------


class ModelAdapter(ABC):
    """Abstract base class for model adapters.

    All model providers must implement this interface.
    """

    def __init__(
        self,
        model_id: str,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.api_key = api_key or ""
        self.api_base = api_base.rstrip("/") if api_base else ""
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
                trust_env=False,
            )
        return self._client

    @abstractmethod
    async def stream_chat(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None = None,
        tools: list[ToolDefinition] | None = None,
        enable_thinking: bool = True,
        json_mode: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream chat completion from the model.

        Args:
            messages: List of message blocks (conversation history).
            system_prompt: Optional system prompt override.
            tools: Optional tool definitions for function calling.
            enable_thinking: Whether to enable thinking/reasoning.
            json_mode: Whether to force JSON output.

        Yields:
            StreamChunk objects containing deltas or final usage.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> ModelCapability:
        """Return the model's capabilities."""
        ...

    @abstractmethod
    def _build_request_body(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None,
        tools: list[ToolDefinition] | None,
        enable_thinking: bool,
        json_mode: bool,
    ) -> dict[str, Any]:
        """Build the API request body."""
        ...

    @abstractmethod
    def _parse_stream_line(self, line: str) -> StreamChunk | None:
        """Parse a single SSE line from the model's stream."""
        ...

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _provider_http_error(
        self,
        provider: str,
        response: httpx.Response,
    ) -> StreamChunk:
        """Read and format a provider HTTP error without leaking credentials."""
        try:
            detail = (await response.aread()).decode("utf-8", errors="replace").strip()
        except Exception:
            detail = ""

        message = (
            f"HTTP {response.status_code}: {detail}"
            if detail
            else f"HTTP {response.status_code}: {response.reason_phrase}"
        )
        logger.error(
            f"{provider} API HTTP error",
            extra={
                "status": response.status_code,
                "detail": detail[:1000],
                "model": self.model_id,
            },
        )
        return StreamChunk(
            type="done",
            content={
                "error": message[:2000],
                "code": f"{provider.upper()}_HTTP_{response.status_code}".replace(" ", "_"),
                "status": response.status_code,
            },
            usage=None,
        )


# ---------------------------------------------------------------------------
# DeepSeek Adapter
# ---------------------------------------------------------------------------


class DeepSeekAdapter(ModelAdapter):
    """Adapter for DeepSeek API (V4-Pro, V4-Flash).

    Features:
    - extra_body thinking parameter
    - reasoning_content / content split
    - JSON mode support
    - Context cache support
    """

    MODEL_MAP = {
        "deepseek-v4-pro": "deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek-v4-flash",
    }

    def __init__(
        self,
        model_id: str,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        super().__init__(
            model_id,
            api_key or settings.deepseek_api_key,
            api_base or settings.deepseek_api_base,
        )

    @property
    def provider_model(self) -> str:
        return self.MODEL_MAP.get(self.model_id, self.model_id)

    def get_capabilities(self) -> ModelCapability:
        from core.config import MODEL_CONFIGS

        cfg = MODEL_CONFIGS.get(self.model_id, {})
        return ModelCapability(
            provider="deepseek",
            model_id=self.model_id,
            context_window=cfg.context_window if hasattr(cfg, "context_window") else 1_000_000,
            max_output_tokens=cfg.max_output_tokens if hasattr(cfg, "max_output_tokens") else 8192,
            supports_vision=cfg.supports_vision if hasattr(cfg, "supports_vision") else False,
            supports_json_mode=True,
            supports_thinking=True,
            supports_context_cache=True,
        )

    def _build_request_body(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None,
        tools: list[ToolDefinition] | None,
        enable_thinking: bool,
        json_mode: bool,
    ) -> dict[str, Any]:
        """Build DeepSeek API request body."""
        # Convert messages to DeepSeek format
        api_messages: list[dict[str, Any]] = []

        # Add system prompt
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            api_msg: dict[str, Any] = {"role": msg.role}

            if msg.content is not None:
                if isinstance(msg.content, str):
                    api_msg["content"] = msg.content
                else:
                    api_msg["content"] = json.dumps(msg.content)

            if msg.tool_calls:
                api_msg["tool_calls"] = msg.tool_calls
            if enable_thinking and msg.role == "assistant" and msg.thinking_content:
                api_msg["reasoning_content"] = msg.thinking_content
            elif msg.role == "assistant" and msg.tool_calls:
                api_msg["reasoning_content"] = "Tool calls prepared."
            if msg.tool_call_id:
                api_msg["tool_call_id"] = msg.tool_call_id

            api_messages.append(api_msg)

        body: dict[str, Any] = {
            "model": self.provider_model,
            "messages": api_messages,
            "stream": True,
        }

        # Product requirement: DeepSeek always uses thinking at max effort.
        body["thinking"] = {
            "type": "enabled",
            "reasoning_effort": "max",
        }

        # Tool definitions
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        # JSON mode
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        return body

    def _parse_stream_line(self, line: str) -> StreamChunk | None:
        """Parse a DeepSeek SSE stream line.

        Handles:
        - Thinking delta (reasoning_content)
        - Text delta (content)
        - Tool call delta (incremental, accumulated into self._tool_call_acc)
        - Usage (final chunk)
        - Done marker ([DONE] or finish_reason)
        """
        if not line.startswith("data: "):
            return None

        data = line[6:]
        if data.strip() == "[DONE]":
            return StreamChunk(type="done", content=None, usage=None)

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return None

        choices = parsed.get("choices", [])
        if not choices:
            usage_data = parsed.get("usage")
            if usage_data:
                return StreamChunk(
                    type="usage",
                    content=None,
                    usage=TokenUsage(
                        input_tokens=usage_data.get("prompt_tokens", 0),
                        output_tokens=usage_data.get("completion_tokens", 0),
                        cached_tokens=usage_data.get("prompt_cache_hit_tokens", 0),
                    ),
                )
            return None

        delta = choices[0].get("delta", {})
        finish_reason = choices[0].get("finish_reason")

        # reasoning_content
        if delta.get("reasoning_content"):
            return StreamChunk(
                type="thinking_delta",
                content=delta["reasoning_content"],
                usage=None,
            )

        # text content
        if delta.get("content"):
            return StreamChunk(
                type="text_delta",
                content=delta["content"],
                usage=None,
            )

        # tool calls — accumulate by index for incremental streaming
        raw_tool_calls = delta.get("tool_calls")
        if raw_tool_calls:
            self._accumulate_tool_calls(raw_tool_calls)

        # If finish_reason is "tool_calls", emit assembled tool_calls as final chunk
        if finish_reason == "tool_calls":
            assembled = self._flush_tool_calls()
            if assembled:
                return StreamChunk(
                    type="done",
                    content=None,
                    usage=None,
                    tool_calls=assembled,
                )

        return None

    # ------------------------------------------------------------------
    # Tool Call Accumulator (for streaming incremental tool_calls)
    # ------------------------------------------------------------------

    def _accumulate_tool_calls(self, raw_tool_calls: list[dict]) -> None:
        """Accumulate incremental streaming tool_calls by index."""
        if not hasattr(self, "_tool_call_acc"):
            self._tool_call_acc: dict[int, dict] = {}
        for tc in raw_tool_calls:
            idx = tc.get("index", 0)
            if idx not in self._tool_call_acc:
                self._tool_call_acc[idx] = {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }
            acc = self._tool_call_acc[idx]
            if "id" in tc and tc["id"]:
                acc["id"] = tc["id"]
            fn = tc.get("function", {})
            if "name" in fn and fn["name"]:
                acc["function"]["name"] = fn["name"]
            if "arguments" in fn:
                acc["function"]["arguments"] += fn["arguments"]

    def _flush_tool_calls(self) -> list[dict] | None:
        """Return assembled tool_calls and reset accumulator."""
        if not hasattr(self, "_tool_call_acc") or not self._tool_call_acc:
            return None
        result = sorted(
            [
                {
                    "id": v["id"],
                    "type": v["type"],
                    "function": {
                        "name": v["function"]["name"],
                        "arguments": v["function"]["arguments"],
                    },
                }
                for v in self._tool_call_acc.values()
            ],
            key=lambda x: x["id"],
        )
        self._tool_call_acc = {}
        return result if result else None

    async def stream_chat(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None = None,
        tools: list[ToolDefinition] | None = None,
        enable_thinking: bool = True,
        json_mode: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream chat completion from DeepSeek API.

        Emits StreamChunks with:
        - thinking_delta: reasoning tokens
        - text_delta: normal content tokens
        - usage: token usage stats
        - done: stream ended; may carry tool_calls field if model called tools
        """
        if not self.api_key:
            yield StreamChunk(
                type="done",
                content={"error": "DEEPSEEK_API_KEY is not configured."},
                usage=None,
            )
            return

        # Reset tool call accumulator for this stream
        self._tool_call_acc = {}

        body = self._build_request_body(
            messages, system_prompt, tools, enable_thinking, json_mode
        )
        client = await self._get_client()

        logger.debug(
            "DeepSeek stream_chat request",
            extra={
                "model": self.model_id,
                "message_count": len(messages),
                "has_tools": bool(tools),
            },
        )

        try:
            async with client.stream(
                "POST",
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                if response.status_code >= 400:
                    yield await self._provider_http_error("DeepSeek", response)
                    return

                async for raw_line in response.aiter_lines():
                    if not raw_line.strip():
                        continue

                    chunk = self._parse_stream_line(raw_line)
                    if chunk:
                        yield chunk

        except httpx.HTTPStatusError as e:
            logger.error(
                "DeepSeek API HTTP error",
                extra={"status": e.response.status_code, "detail": str(e)},
            )
            yield StreamChunk(
                type="done",
                content={"error": f"HTTP {e.response.status_code}: {str(e)}"},
                usage=None,
            )
        except Exception as e:
            logger.error("DeepSeek API error", extra={"error": str(e)})
            yield StreamChunk(
                type="done",
                content={"error": str(e)},
                usage=None,
            )


# ---------------------------------------------------------------------------
# Kimi Adapter
# ---------------------------------------------------------------------------


class KimiAdapter(ModelAdapter):
    """Adapter for Kimi/Moonshot API (K2.6, K2.5).

    Features:
    - reasoning_content handling
    - Image base64 injection for vision
    - JSON mode support
    - Context cache support (automatic)
    """

    MODEL_MAP = {
        "kimi-k2-6": "kimi-k2.6",
        "kimi-k2-5": "kimi-k2.5",
    }

    def __init__(
        self,
        model_id: str,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> None:
        super().__init__(
            model_id,
            api_key or settings.kimi_api_key,
            api_base or settings.kimi_api_base,
        )

    @property
    def provider_model(self) -> str:
        return self.MODEL_MAP.get(self.model_id, self.model_id)

    def get_capabilities(self) -> ModelCapability:
        from core.config import MODEL_CONFIGS

        cfg = MODEL_CONFIGS.get(self.model_id, {})
        return ModelCapability(
            provider="kimi",
            model_id=self.model_id,
            context_window=cfg.context_window if hasattr(cfg, "context_window") else 256_000,
            max_output_tokens=cfg.max_output_tokens if hasattr(cfg, "max_output_tokens") else 8192,
            supports_vision=cfg.supports_vision if hasattr(cfg, "supports_vision") else True,
            supports_json_mode=True,
            supports_thinking=True,
            supports_context_cache=True,
        )

    def _build_request_body(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None,
        tools: list[ToolDefinition] | None,
        enable_thinking: bool,
        json_mode: bool,
    ) -> dict[str, Any]:
        """Build Kimi API request body."""
        api_messages: list[dict[str, Any]] = []

        # Add system prompt
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})

        for msg in messages:
            api_msg: dict[str, Any] = {"role": msg.role}

            if msg.content is not None:
                if isinstance(msg.content, str):
                    api_msg["content"] = self._process_content_for_vision(msg.content)
                else:
                    api_msg["content"] = msg.content

            if msg.tool_calls:
                api_msg["tool_calls"] = msg.tool_calls
            if enable_thinking and msg.role == "assistant" and msg.thinking_content:
                api_msg["reasoning_content"] = msg.thinking_content
            elif msg.role == "assistant" and msg.tool_calls:
                api_msg["reasoning_content"] = "Tool calls prepared."
            if msg.tool_call_id:
                api_msg["tool_call_id"] = msg.tool_call_id

            api_messages.append(api_msg)

        body: dict[str, Any] = {
            "model": self.provider_model,
            "messages": api_messages,
            "stream": True,
            "thinking": {"type": "enabled"},
        }

        # Tool definitions
        if tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]

        # JSON mode
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        return body

    def _process_content_for_vision(
        self, content: str
    ) -> str | list[dict[str, Any]]:
        """Process content to inject base64 images for vision support.

        Detects image references in content and converts to multimodal format.
        """
        # Simple detection: if content references an image path/URL
        # For now, return as-is; full implementation will parse image references
        # and convert to base64 content blocks
        if content.startswith("![") and "](" in content:
            # Contains markdown image - could convert to vision format
            return content
        return content

    def _parse_stream_line(self, line: str) -> StreamChunk | None:
        """Parse a Kimi SSE stream line.

        Handles:
        - Thinking delta (reasoning_content)
        - Text delta (content)
        - Tool call delta (incremental, accumulated)
        - Usage (final chunk)
        - Done marker
        """
        if not line.startswith("data: "):
            return None

        data = line[6:]
        if data.strip() == "[DONE]":
            return StreamChunk(type="done", content=None, usage=None)

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return None

        choices = parsed.get("choices", [])
        if not choices:
            usage_data = parsed.get("usage")
            if usage_data:
                return StreamChunk(
                    type="usage",
                    content=None,
                    usage=TokenUsage(
                        input_tokens=usage_data.get("prompt_tokens", 0),
                        output_tokens=usage_data.get("completion_tokens", 0),
                        cached_tokens=usage_data.get("cached_tokens", 0),
                    ),
                )
            return None

        delta = choices[0].get("delta", {})
        finish_reason = choices[0].get("finish_reason")

        if delta.get("reasoning_content"):
            return StreamChunk(
                type="thinking_delta",
                content=delta["reasoning_content"],
                usage=None,
            )

        if delta.get("content"):
            return StreamChunk(
                type="text_delta",
                content=delta["content"],
                usage=None,
            )

        raw_tool_calls = delta.get("tool_calls")
        if raw_tool_calls:
            self._accumulate_tool_calls(raw_tool_calls)

        if finish_reason == "tool_calls":
            assembled = self._flush_tool_calls()
            if assembled:
                return StreamChunk(
                    type="done",
                    content=None,
                    usage=None,
                    tool_calls=assembled,
                )

        return None

    def _accumulate_tool_calls(self, raw_tool_calls: list[dict]) -> None:
        """Accumulate incremental streaming tool_calls by index."""
        if not hasattr(self, "_tool_call_acc"):
            self._tool_call_acc: dict[int, dict] = {}
        for tc in raw_tool_calls:
            idx = tc.get("index", 0)
            if idx not in self._tool_call_acc:
                self._tool_call_acc[idx] = {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                }
            acc = self._tool_call_acc[idx]
            if "id" in tc and tc["id"]:
                acc["id"] = tc["id"]
            fn = tc.get("function", {})
            if "name" in fn and fn["name"]:
                acc["function"]["name"] = fn["name"]
            if "arguments" in fn:
                acc["function"]["arguments"] += fn["arguments"]

    def _flush_tool_calls(self) -> list[dict] | None:
        """Return assembled tool_calls and reset accumulator."""
        if not hasattr(self, "_tool_call_acc") or not self._tool_call_acc:
            return None
        result = sorted(
            [
                {
                    "id": v["id"],
                    "type": v["type"],
                    "function": {
                        "name": v["function"]["name"],
                        "arguments": v["function"]["arguments"],
                    },
                }
                for v in self._tool_call_acc.values()
            ],
            key=lambda x: x["id"],
        )
        self._tool_call_acc = {}
        return result if result else None

    async def stream_chat(
        self,
        messages: list[MessageBlock],
        system_prompt: str | None = None,
        tools: list[ToolDefinition] | None = None,
        enable_thinking: bool = True,
        json_mode: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream chat completion from Kimi API."""
        if not self.api_key:
            yield StreamChunk(
                type="done",
                content={"error": "KIMI_API_KEY is not configured."},
                usage=None,
            )
            return

        # Reset tool call accumulator
        self._tool_call_acc = {}

        body = self._build_request_body(
            messages, system_prompt, tools, enable_thinking, json_mode
        )
        client = await self._get_client()

        logger.debug(
            "Kimi stream_chat request",
            extra={"model": self.model_id, "message_count": len(messages)},
        )

        try:
            async with client.stream(
                "POST",
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            ) as response:
                if response.status_code >= 400:
                    yield await self._provider_http_error("Kimi", response)
                    return

                async for raw_line in response.aiter_lines():
                    if not raw_line.strip():
                        continue

                    chunk = self._parse_stream_line(raw_line)
                    if chunk:
                        yield chunk

        except httpx.HTTPStatusError as e:
            logger.error(
                "Kimi API HTTP error",
                extra={"status": e.response.status_code, "detail": str(e)},
            )
            yield StreamChunk(
                type="done",
                content={"error": f"HTTP {e.response.status_code}: {str(e)}"},
                usage=None,
            )
        except Exception as e:
            logger.error("Kimi API error", extra={"error": str(e)})
            yield StreamChunk(
                type="done",
                content={"error": str(e)},
                usage=None,
            )


# ---------------------------------------------------------------------------
# Model Adapter Factory
# ---------------------------------------------------------------------------


class ModelAdapterFactory:
    """Factory for creating model adapters."""

    _adapters: dict[str, type[ModelAdapter]] = {
        "deepseek-v4-pro": DeepSeekAdapter,
        "deepseek-v4-flash": DeepSeekAdapter,
        "kimi-k2-6": KimiAdapter,
        "kimi-k2-5": KimiAdapter,
    }

    @classmethod
    def create(
        cls,
        model_id: str,
        api_key: str | None = None,
        api_base: str | None = None,
    ) -> ModelAdapter:
        """Create a model adapter for the given model ID.

        Args:
            model_id: Model identifier (e.g., 'deepseek-v4-pro').
            api_key: Optional API key override.

        Returns:
            Configured ModelAdapter instance.

        Raises:
            ValueError: If model_id is not supported.
        """
        adapter_class = cls._adapters.get(model_id)
        if adapter_class is None:
            raise ValueError(
                f"Unsupported model: {model_id}. "
                f"Available: {list(cls._adapters.keys())}"
            )
        return adapter_class(model_id=model_id, api_key=api_key, api_base=api_base)

    @classmethod
    def register(
        cls, model_id: str, adapter_class: type[ModelAdapter]
    ) -> None:
        """Register a new adapter class for a model ID."""
        cls._adapters[model_id] = adapter_class

    @classmethod
    def list_models(cls) -> list[str]:
        """List all supported model IDs."""
        return list(cls._adapters.keys())
