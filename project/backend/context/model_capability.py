"""Model Capability Registry for Context OS v2.

Defines the canonical ``ModelCapability`` schema and a registry that can:
    - Load capabilities from a YAML file
    - Register models programmatically
    - Resolve a model_id to its capabilities at runtime

All model metadata lives here so the rest of the system never hard-codes
model-specific constants.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Model Capability Schema
# ---------------------------------------------------------------------------


class ModelCapability(BaseModel):
    """Capabilities of a specific LLM.

    Attributes:
        provider: API provider name (e.g. 'deepseek', 'openai', 'kimi').
        model_id: Canonical model identifier (e.g. 'deepseek-chat').
        context_window: Total context-window size in tokens.
        max_output_tokens: Max tokens the model can emit in one response.
        supports_tool_call: Whether the model supports function/tool calling.
        supports_vision: Whether the model supports image/video input.
        supports_json_mode: Whether the model supports forced JSON output.
        supports_thinking: Whether the model exposes reasoning/thinking content.
        supports_prefix_cache: Whether the provider supports KV-cache prefix reuse.
        supports_context_cache: Whether the provider supports context caching.
    """

    provider: str
    model_id: str
    context_window: int = Field(..., gt=0)
    max_output_tokens: int = Field(..., gt=0)
    supports_tool_call: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_thinking: bool = False
    supports_prefix_cache: bool = False
    supports_context_cache: bool = False

    # Capability hash for cache-invalidation checks
    _cached_hash: str | None = None

    @field_validator("context_window", "max_output_tokens")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    @property
    def capability_hash(self) -> str:
        """Return a SHA-256 hash of this capability descriptor.

        Used by downstream components to detect when a model's
        capabilities have changed and invalidate cached decisions.
        """
        if self._cached_hash is None:
            payload = (
                f"{self.provider}|{self.model_id}|{self.context_window}|"
                f"{self.max_output_tokens}|{self.supports_tool_call}|"
                f"{self.supports_vision}|{self.supports_json_mode}|"
                f"{self.supports_thinking}|{self.supports_prefix_cache}|"
                f"{self.supports_context_cache}"
            )
            self._cached_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return self._cached_hash

    def fits_within_window(self, input_tokens: int, output_tokens: int) -> bool:
        """Check if a (input, output) pair fits within this model's window.

        Args:
            input_tokens: Estimated input token count.
            output_tokens: Desired output token count.

        Returns:
            True if the sum fits with a 5 % internal padding.
        """
        padding = int(self.context_window * 0.05)
        return (input_tokens + output_tokens + padding) <= self.context_window

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dictionary."""
        return self.model_dump()


# ---------------------------------------------------------------------------
# Capability Registry
# ---------------------------------------------------------------------------


class ModelCapabilityRegistry:
    """Central registry for model capabilities.

    Supports:
        - Programmatic registration (code-level defaults)
        - YAML file loading (admin-configurable overrides)
        - Runtime resolution by model_id
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._models: dict[str, ModelCapability] = {}

    # -- Registration --------------------------------------------------

    def register(self, capability: ModelCapability) -> None:
        """Register or overwrite a model capability.

        Args:
            capability: ModelCapability instance to register.
        """
        self._models[capability.model_id] = capability
        logger.debug(
            "Registered model capability",
            extra={
                "model_id": capability.model_id,
                "provider": capability.provider,
                "context_window": capability.context_window,
            },
        )

    def register_many(self, capabilities: list[ModelCapability]) -> None:
        """Bulk-register model capabilities.

        Args:
            capabilities: List of ModelCapability instances.
        """
        for cap in capabilities:
            self.register(cap)

    def unregister(self, model_id: str) -> bool:
        """Remove a model from the registry.

        Args:
            model_id: Model identifier to remove.

        Returns:
            True if the model was present and removed.
        """
        return self._models.pop(model_id, None) is not None

    # -- Resolution ----------------------------------------------------

    def resolve(self, model_id: str) -> ModelCapability:
        """Resolve a model_id to its capability descriptor.

        Args:
            model_id: Canonical model identifier.

        Returns:
            ModelCapability instance.

        Raises:
            ValueError: If the model_id is not registered.
        """
        if model_id not in self._models:
            available = ", ".join(sorted(self._models.keys()))
            raise ValueError(
                f"Unknown model_id: '{model_id}'. Available: {available}"
            )
        return self._models[model_id]

    def resolve_or_default(
        self,
        model_id: str,
        default: ModelCapability | None = None,
    ) -> ModelCapability:
        """Resolve a model_id, falling back to a default if not found.

        Args:
            model_id: Canonical model identifier.
            default: Fallback capability if model_id is unknown.

        Returns:
            ModelCapability instance.

        Raises:
            ValueError: If the model_id is unknown and no default is provided.
        """
        if model_id in self._models:
            return self._models[model_id]
        if default is not None:
            return default
        raise ValueError(f"Unknown model_id: '{model_id}' and no default provided")

    def list_models(self) -> list[str]:
        """List all registered model_ids."""
        return sorted(self._models.keys())

    def is_registered(self, model_id: str) -> bool:
        """Check if a model_id is registered."""
        return model_id in self._models

    def all_capabilities(self) -> list[ModelCapability]:
        """Return all registered capabilities."""
        return list(self._models.values())

    # -- YAML Loading --------------------------------------------------

    def load_from_yaml(self, path: str | Path) -> int:
        """Load model capabilities from a YAML file.

        Expected YAML structure::

            models:
              - provider: deepseek
                model_id: deepseek-chat
                context_window: 65536
                max_output_tokens: 8192
                supports_tool_call: true
                ...

        Args:
            path: Path to the YAML file.

        Returns:
            Number of models loaded.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the YAML structure is invalid.
        """
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Capability YAML not found: {p}")

        with p.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict) or "models" not in data:
            raise ValueError(
                f"Invalid YAML structure in {p}: expected top-level 'models' key"
            )

        loaded = 0
        for entry in data["models"]:
            if not isinstance(entry, dict):
                logger.warning("Skipping non-dict entry in capability YAML")
                continue
            try:
                cap = ModelCapability(**entry)
                self.register(cap)
                loaded += 1
            except Exception as e:
                model_id = entry.get("model_id", "<unknown>")
                logger.warning(
                    f"Failed to load capability for '{model_id}': {e}"
                )

        logger.info(
            "Loaded model capabilities from YAML",
            extra={"path": str(p), "count": loaded},
        )
        return loaded

    def load_from_env(self) -> int:
        """Attempt to load capabilities from the path in ``CAPABILITIES_YAML`` env var.

        Returns:
            Number of models loaded (0 if env var not set or file missing).
        """
        env_path = os.getenv("CAPABILITIES_YAML")
        if not env_path:
            return 0
        try:
            return self.load_from_yaml(env_path)
        except FileNotFoundError:
            logger.warning(
                "CAPABILITIES_YAML points to missing file",
                extra={"path": env_path},
            )
            return 0

    # -- Inspection ----------------------------------------------------

    def get_registry_hash(self) -> str:
        """Return a hash representing the current registry state.

        Useful for cache-invalidation: if the hash changes, any
        downstream cache keyed on model capabilities is stale.
        """
        ids = ",".join(sorted(self._models.keys()))
        hashes = "|".join(
            self._models[mid].capability_hash for mid in sorted(self._models)
        )
        payload = f"{ids}::{hashes}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Global Registry Instance + Convenience Functions
# ---------------------------------------------------------------------------

_registry: ModelCapabilityRegistry | None = None


def get_registry() -> ModelCapabilityRegistry:
    """Get the singleton registry instance (initialised with defaults on first call)."""
    global _registry
    if _registry is None:
        _registry = ModelCapabilityRegistry()
        _register_builtins(_registry)
        # Attempt to overlay YAML overrides
        _registry.load_from_env()
    return _registry


def resolve_model_capability(model_id: str) -> ModelCapability:
    """Resolve *model_id* to its capability descriptor.

    Convenience wrapper around the global registry.
    """
    return get_registry().resolve(model_id)


def list_registered_models() -> list[str]:
    """List all registered model IDs."""
    return get_registry().list_models()


def register_model_capability(capability: ModelCapability) -> None:
    """Register a model capability in the global registry."""
    get_registry().register(capability)


# ---------------------------------------------------------------------------
# Builtin Defaults
# ---------------------------------------------------------------------------


def _register_builtins(reg: ModelCapabilityRegistry) -> None:
    """Register well-known models as sensible defaults.

    These can be overwritten by YAML-loaded entries or by explicit
    ``register()`` calls after initialisation.
    """
    builtins = [
        # DeepSeek
        ModelCapability(
            provider="deepseek",
            model_id="deepseek-chat",
            context_window=65536,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=False,
            supports_json_mode=True,
            supports_thinking=False,
            supports_prefix_cache=True,
            supports_context_cache=False,
        ),
        ModelCapability(
            provider="deepseek",
            model_id="deepseek-reasoner",
            context_window=65536,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=False,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=True,
            supports_context_cache=False,
        ),
        # DeepSeek V4 (project-specific naming)
        ModelCapability(
            provider="deepseek",
            model_id="deepseek-v4-pro",
            context_window=256_000,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=False,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=True,
            supports_context_cache=True,
        ),
        ModelCapability(
            provider="deepseek",
            model_id="deepseek-v4-flash",
            context_window=256_000,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=False,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=True,
            supports_context_cache=True,
        ),
        # Kimi / Moonshot
        ModelCapability(
            provider="kimi",
            model_id="kimi-k2-6",
            context_window=256_000,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=True,
            supports_context_cache=True,
        ),
        ModelCapability(
            provider="kimi",
            model_id="kimi-k2-5",
            context_window=256_000,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=True,
            supports_context_cache=True,
        ),
        # OpenAI
        ModelCapability(
            provider="openai",
            model_id="gpt-4o",
            context_window=128_000,
            max_output_tokens=4096,
            supports_tool_call=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_thinking=False,
            supports_prefix_cache=False,
            supports_context_cache=True,
        ),
        # Anthropic
        ModelCapability(
            provider="anthropic",
            model_id="claude-sonnet-4",
            context_window=200_000,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=True,
            supports_context_cache=True,
        ),
        # Google
        ModelCapability(
            provider="google",
            model_id="gemini-2.5-pro",
            context_window=1_000_000,
            max_output_tokens=8192,
            supports_tool_call=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_thinking=True,
            supports_prefix_cache=False,
            supports_context_cache=False,
        ),
    ]
    reg.register_many(builtins)
