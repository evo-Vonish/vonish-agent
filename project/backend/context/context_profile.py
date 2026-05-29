"""Context Profile configuration for the Agent system.

Defines context profiles as Pydantic BaseModels per Context OS v2 spec.
Three tiers: cheap, balanced, max — plus model-aware auto-scaling.

Key design principles:
    - Profiles are immutable values (frozen BaseModel instances).
    - Auto-scaling adapts a profile when the model's context_window is smaller
      than the profile's max_input_tokens.
    - All new v2 fields (safety_margin_ratio, output_reserve_tokens, etc.)
      are included with tier-appropriate defaults.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Type Aliases
# ---------------------------------------------------------------------------

ContextProfileName = Literal["cheap", "balanced", "max", "custom"]
ToolResultMode = Literal["summary", "hybrid", "verbose"]
MultimodalMode = Literal["caption_only", "caption_plus_refs", "rich"]
CompressionLevel = Literal["aggressive", "balanced", "minimal"]


# ---------------------------------------------------------------------------
# Context Profile (Pydantic BaseModel)
# ---------------------------------------------------------------------------


class ContextProfile(BaseModel):
    """Context profile defining resource allocation strategy.

    Attributes:
        name: Profile tier name (cheap / balanced / max / custom).
        max_input_tokens: Maximum input tokens for the context window.
        recent_turns: Number of recent conversation turns (Sacred Window).
        memory_top_k: Number of memory items to recall.
        workspace_chunk_top_k: Number of workspace chunks to retrieve.
        tool_result_mode: How to handle tool results (summary / hybrid / verbose).
        multimodal_mode: How to handle multimodal content.
        compression_level: Compression aggressiveness.
        safety_margin_ratio: Fraction of context_window reserved as safety margin.
        output_reserve_tokens: Tokens reserved for model output.
        max_tool_result_tokens: Max tokens per individual tool result.
        enable_cycle_advance: Whether to enable cycle advancement for long sessions.
        min_recent_messages: Absolute minimum sacred-window messages.
    """

    name: ContextProfileName = "balanced"
    max_input_tokens: int = Field(..., gt=0, description="Maximum input tokens")
    recent_turns: int = Field(..., ge=0, description="Sacred Window size in turns")
    memory_top_k: int = Field(..., ge=0, description="Memory recall top-k")
    workspace_chunk_top_k: int = Field(..., ge=0, description="Workspace chunk top-k")
    tool_result_mode: ToolResultMode = "hybrid"
    multimodal_mode: MultimodalMode = "caption_plus_refs"
    compression_level: CompressionLevel = "balanced"
    safety_margin_ratio: float = Field(..., ge=0.0, le=0.9, description="Safety margin ratio")
    output_reserve_tokens: int = Field(..., ge=0, description="Output reservation in tokens")
    max_tool_result_tokens: int = Field(..., gt=0, description="Max tokens per tool result")
    enable_cycle_advance: bool = True
    min_recent_messages: int = Field(..., ge=1, description="Minimum sacred window messages")

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("safety_margin_ratio")
    @classmethod
    def _check_safety_margin(cls, v: float) -> float:
        if v < 0.0 or v > 0.9:
            raise ValueError("safety_margin_ratio must be between 0.0 and 0.9")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> ContextProfile:
        """Ensure profile parameters are internally consistent."""
        # min_recent_messages must not exceed recent_turns * 2 (user+assistant pairs)
        if self.min_recent_messages > self.recent_turns * 2:
            raise ValueError(
                f"min_recent_messages ({self.min_recent_messages}) cannot exceed "
                f"recent_turns * 2 ({self.recent_turns * 2})"
            )
        return self

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Convert profile to plain dictionary."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextProfile:
        """Create a ContextProfile from a dictionary.

        Args:
            data: Dictionary containing profile fields.

        Returns:
            ContextProfile instance.
        """
        # Allow unknown fields to be ignored for forward compatibility
        known = {f for f in cls.model_fields}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    # ------------------------------------------------------------------
    # Convenience factory
    # ------------------------------------------------------------------

    @classmethod
    def create_custom(
        cls,
        max_input_tokens: int = 96000,
        recent_turns: int = 16,
        memory_top_k: int = 12,
        workspace_chunk_top_k: int = 8,
        tool_result_mode: ToolResultMode = "hybrid",
        multimodal_mode: MultimodalMode = "caption_plus_refs",
        compression_level: CompressionLevel = "balanced",
        safety_margin_ratio: float = 0.35,
        output_reserve_tokens: int = 8192,
        max_tool_result_tokens: int = 8000,
        enable_cycle_advance: bool = True,
        min_recent_messages: int = 6,
        **kwargs: Any,
    ) -> ContextProfile:
        """Create a custom context profile.

        Args:
            max_input_tokens: Maximum input tokens.
            recent_turns: Sacred Window turns.
            memory_top_k: Memory recall count.
            workspace_chunk_top_k: Workspace chunk retrieval count.
            tool_result_mode: Tool result handling mode.
            multimodal_mode: Multimodal content handling mode.
            compression_level: Compression aggressiveness.
            safety_margin_ratio: Safety margin as ratio of context window.
            output_reserve_tokens: Tokens reserved for model output.
            max_tool_result_tokens: Max tokens per tool result.
            enable_cycle_advance: Enable cycle advancement.
            min_recent_messages: Minimum sacred window messages.
            **kwargs: Ignored, for forward compatibility.

        Returns:
            Custom ContextProfile instance with name='custom'.
        """
        return cls(
            name="custom",
            max_input_tokens=max_input_tokens,
            recent_turns=recent_turns,
            memory_top_k=memory_top_k,
            workspace_chunk_top_k=workspace_chunk_top_k,
            tool_result_mode=tool_result_mode,
            multimodal_mode=multimodal_mode,
            compression_level=compression_level,
            safety_margin_ratio=safety_margin_ratio,
            output_reserve_tokens=output_reserve_tokens,
            max_tool_result_tokens=max_tool_result_tokens,
            enable_cycle_advance=enable_cycle_advance,
            min_recent_messages=min_recent_messages,
        )


# ---------------------------------------------------------------------------
# Predefined Profiles (Context OS v2 defaults)
# ---------------------------------------------------------------------------

# Cheap: cost-sensitive, small models, aggressive compression
CONTEXT_PROFILE_CHEAP = ContextProfile(
    name="cheap",
    max_input_tokens=32000,
    recent_turns=6,
    memory_top_k=5,
    workspace_chunk_top_k=3,
    tool_result_mode="summary",
    multimodal_mode="caption_only",
    compression_level="aggressive",
    safety_margin_ratio=0.40,
    output_reserve_tokens=4096,
    max_tool_result_tokens=2000,
    enable_cycle_advance=True,
    min_recent_messages=4,
)

# Balanced: default for most scenarios
CONTEXT_PROFILE_BALANCED = ContextProfile(
    name="balanced",
    max_input_tokens=96000,
    recent_turns=16,
    memory_top_k=12,
    workspace_chunk_top_k=8,
    tool_result_mode="hybrid",
    multimodal_mode="caption_plus_refs",
    compression_level="balanced",
    safety_margin_ratio=0.35,
    output_reserve_tokens=8192,
    max_tool_result_tokens=8000,
    enable_cycle_advance=True,
    min_recent_messages=6,
)

# Max: large models, rich context, minimal compression
CONTEXT_PROFILE_MAX = ContextProfile(
    name="max",
    max_input_tokens=256000,
    recent_turns=50,
    memory_top_k=30,
    workspace_chunk_top_k=20,
    tool_result_mode="verbose",
    multimodal_mode="rich",
    compression_level="minimal",
    safety_margin_ratio=0.25,
    output_reserve_tokens=8192,
    max_tool_result_tokens=20000,
    enable_cycle_advance=True,
    min_recent_messages=10,
)

# Custom: defaults to balanced settings, user-modifiable
CONTEXT_PROFILE_CUSTOM = ContextProfile(
    name="custom",
    max_input_tokens=96000,
    recent_turns=16,
    memory_top_k=12,
    workspace_chunk_top_k=8,
    tool_result_mode="hybrid",
    multimodal_mode="caption_plus_refs",
    compression_level="balanced",
    safety_margin_ratio=0.35,
    output_reserve_tokens=8192,
    max_tool_result_tokens=8000,
    enable_cycle_advance=True,
    min_recent_messages=6,
)

CONTEXT_PROFILES: dict[str, ContextProfile] = {
    "cheap": CONTEXT_PROFILE_CHEAP,
    "balanced": CONTEXT_PROFILE_BALANCED,
    "max": CONTEXT_PROFILE_MAX,
    "custom": CONTEXT_PROFILE_CUSTOM,
}


# ---------------------------------------------------------------------------
# Profile Access Functions
# ---------------------------------------------------------------------------


def get_profile(name: str) -> ContextProfile:
    """Get a context profile by name.

    Args:
        name: Profile name ('cheap', 'balanced', 'max', 'custom').

    Returns:
        ContextProfile instance (a copy, safe to modify).

    Raises:
        ValueError: If profile name is not found.
    """
    if name not in CONTEXT_PROFILES:
        available = ", ".join(CONTEXT_PROFILES.keys())
        raise ValueError(f"Unknown context profile: '{name}'. Available: {available}")
    # Return a copy so callers can mutate without affecting the global
    return CONTEXT_PROFILES[name].model_copy(deep=True)


def list_profiles() -> list[str]:
    """List all available profile names."""
    return list(CONTEXT_PROFILES.keys())


def get_profile_for_model(model_context_window: int) -> str:
    """Suggest a profile name based on model context window size.

    Args:
        model_context_window: Model's context window size in tokens.

    Returns:
        Recommended profile name.
    """
    if model_context_window >= 500_000:
        return "max"
    elif model_context_window >= 100_000:
        return "balanced"
    else:
        return "cheap"


def update_custom_profile(profile: ContextProfile) -> None:
    """Update the custom profile in the registry.

    Args:
        profile: New custom profile to register. The name is forced to 'custom'.
    """
    updated = profile.model_copy(update={"name": "custom"}, deep=True)
    CONTEXT_PROFILES["custom"] = updated


# ---------------------------------------------------------------------------
# Model-Aware Auto-Scaling
# ---------------------------------------------------------------------------

def scale_profile_for_model(
    profile: ContextProfile,
    model_capability: "ModelCapability",  # noqa: F821
) -> ContextProfile:
    """Auto-scale a profile when the model's context_window is smaller than needed.

    When ``model_capability.context_window < profile.max_input_tokens``:
        - max_input_tokens  -> model.context_window * 0.8
        - recent_turns      -> min(profile.recent_turns, 8)
        - multimodal_mode   -> 'caption_only' (downgrade)
        - tool_result_mode  -> 'summary' (downgrade)
        - safety_margin_ratio += 0.05 (more conservative)
        - memory_top_k      -> min(profile.memory_top_k, 8)

    Args:
        profile: The requested context profile.
        model_capability: The actual model's capability descriptor.

    Returns:
        A *new* ContextProfile (original is never mutated).
    """
    # Defer import to avoid circular dependency at module load time
    from context.model_capability import ModelCapability as MC

    if not isinstance(model_capability, MC):
        raise TypeError(
            f"model_capability must be ModelCapability, got {type(model_capability).__name__}"
        )

    if model_capability.context_window >= profile.max_input_tokens:
        # No scaling needed — but still return a copy for consistency
        return profile.model_copy(deep=True)

    # Scaling required: compute new values
    new_max_input = int(model_capability.context_window * 0.8)
    new_recent_turns = min(profile.recent_turns, 8)
    new_safety_margin = min(profile.safety_margin_ratio + 0.05, 0.85)
    new_memory_top_k = min(profile.memory_top_k, 8)

    # Downgrade modes when window is tight
    new_multimodal_mode: MultimodalMode = "caption_only"
    new_tool_result_mode: ToolResultMode = "summary"

    scaled = profile.model_copy(
        update={
            "max_input_tokens": new_max_input,
            "recent_turns": new_recent_turns,
            "multimodal_mode": new_multimodal_mode,
            "tool_result_mode": new_tool_result_mode,
            "safety_margin_ratio": new_safety_margin,
            "memory_top_k": new_memory_top_k,
        },
        deep=True,
    )
    return scaled
