"""Token Budget management for Context OS v2.

Implements progressive compression thresholds (70 % / 80 % / 85 % / 90 % / 99 %)
and a component-level budget calculator that divides the available input budget
into allocations for system_prompt, user_memory, recent_messages, tool_results,
tool_definitions, workspace_refs, and current_query.

Usage::

    from context.token_budget import calculate_token_budget, TokenBudget

    budget = calculate_token_budget(profile, model_capability)
    status = budget.check_budget()

    if status.compression_level != "none":
        # trigger compression
        ...
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

CompressionLevelName = Literal[
    "none",
    "light",       # 70 % — mild compression of oldest content
    "moderate",    # 80 % — compress beyond recent_turns
    "heavy",       # 85 % — compress tool results, reduce memories
    "extreme",     # 90 % — aggressive reduction
    "emergency",   # 99 % — keep only essentials
]

# ---------------------------------------------------------------------------
# Thresholds (ordered from lowest to highest)
# ---------------------------------------------------------------------------

THRESHOLDS: list[tuple[float, CompressionLevelName]] = [
    (0.70, "light"),
    (0.80, "moderate"),
    (0.85, "heavy"),
    (0.90, "extreme"),
    (0.99, "emergency"),
]

_COMPRESSION_DESCRIPTIONS: dict[CompressionLevelName, str] = {
    "none": "No compression needed. Token usage is healthy.",
    "light": "Mild compression: compress oldest message summaries beyond 2x recent_turns.",
    "moderate": "Moderate compression: compress all messages beyond recent_turns to summaries.",
    "heavy": "Heavy compression: compress tool results to summaries, reduce memory recall.",
    "extreme": "Extreme compression: aggressively reduce non-essential context components.",
    "emergency": "Emergency mode: keep only last 3 turns + core system prompt.",
}

# ---------------------------------------------------------------------------
# Token Budget (Pydantic model)
# ---------------------------------------------------------------------------


class TokenBudget(BaseModel):
    """Token budget with component-level allocation.

    Attributes:
        context_window: Total model context-window size.
        output_reserved: Tokens reserved for model output.
        safety_margin_tokens: Tokens reserved as safety margin.
        available_input_budget: Tokens actually available for input.
        breakdown: Per-component token budget caps.
        used_tokens: Currently consumed tokens (mutable at runtime).
    """

    context_window: int = Field(..., gt=0, description="Model context window size")
    output_reserved: int = Field(..., ge=0, description="Reserved for model output")
    safety_margin_tokens: int = Field(..., ge=0, description="Safety margin in tokens")
    available_input_budget: int = Field(..., gt=0, description="Available input budget")
    breakdown: dict[str, int] = Field(
        default_factory=dict,
        description="Per-component budget caps",
    )
    used_tokens: int = Field(default=0, ge=0, description="Currently used tokens")

    @field_validator("available_input_budget")
    @classmethod
    def _check_budget_positive(cls, v: int, info: Any) -> int:  # noqa: ANN401
        if v <= 0:
            data = info.data
            raise ValueError(
                f"available_input_budget must be positive: "
                f"context_window={data.get('context_window')}, "
                f"output_reserved={data.get('output_reserved')}, "
                f"safety_margin={data.get('safety_margin_tokens')}"
            )
        return v

    # -- Budget status -------------------------------------------------

    @property
    def usage_ratio(self) -> float:
        """Current usage ratio (0.0 to 1.0+)."""
        if self.available_input_budget <= 0:
            return 1.0
        return self.used_tokens / self.available_input_budget

    @property
    def remaining_tokens(self) -> int:
        """Remaining tokens before the input budget is exhausted."""
        return max(0, self.available_input_budget - self.used_tokens)

    def set_usage(self, tokens: int) -> None:
        """Set current token usage to an absolute value.

        Args:
            tokens: Current number of tokens used.
        """
        self.used_tokens = max(0, tokens)

    def add_usage(self, tokens: int) -> None:
        """Add to current token usage.

        Args:
            tokens: Number of tokens to add.
        """
        self.used_tokens += max(0, tokens)

    def subtract_usage(self, tokens: int) -> None:
        """Subtract from current token usage (e.g. after compression).

        Args:
            tokens: Number of tokens to subtract.
        """
        self.used_tokens = max(0, self.used_tokens - max(0, tokens))

    def check_budget(self) -> BudgetStatus:
        """Check current budget status and determine compression level.

        Returns:
            BudgetStatus with usage ratio and recommended compression level.
        """
        ratio = self.usage_ratio
        level = self.get_compression_level(ratio)
        return BudgetStatus(
            current_tokens=self.used_tokens,
            max_tokens=self.available_input_budget,
            usage_ratio=ratio,
            compression_level=level,
            is_over_budget=ratio >= 1.0,
            remaining_tokens=self.remaining_tokens,
        )

    def get_compression_level(
        self, ratio: float | None = None
    ) -> CompressionLevelName:
        """Compression is disabled; over-budget callers must reject the request."""
        return "none"

    def would_exceed(self, additional_tokens: int) -> bool:
        """Check if adding tokens would exceed budget.

        Args:
            additional_tokens: Tokens to potentially add.

        Returns:
            True if budget would be exceeded.
        """
        return (self.used_tokens + additional_tokens) > self.available_input_budget

    def reserve(self, tokens: int) -> bool:
        """Reserve a portion of the budget.

        Args:
            tokens: Number of tokens to reserve.

        Returns:
            True if reservation succeeded, False if it would exceed budget.
        """
        if self.would_exceed(tokens):
            return False
        self.used_tokens += tokens
        return True

    def reset(self) -> None:
        """Reset current token usage to zero."""
        self.used_tokens = 0

    def get_component_budget(self, component: str) -> int:
        """Get the budget cap for a named component.

        Args:
            component: Component name (e.g. 'system_prompt', 'recent_messages').

        Returns:
            Token budget cap (0 if component not in breakdown).
        """
        return self.breakdown.get(component, 0)

    def __repr__(self) -> str:
        return (
            f"TokenBudget({self.used_tokens}/{self.available_input_budget} "
            f"= {self.usage_ratio:.1%})"
        )

    def __str__(self) -> str:
        status = self.check_budget()
        return (
            f"TokenBudget: {self.used_tokens:,}/{self.available_input_budget:,} "
            f"({self.usage_ratio:.1%}) — {status.compression_level}"
        )


# ---------------------------------------------------------------------------
# Budget Status
# ---------------------------------------------------------------------------


class BudgetStatus(BaseModel):
    """Current status of the token budget."""

    current_tokens: int
    max_tokens: int
    usage_ratio: float
    compression_level: CompressionLevelName
    is_over_budget: bool
    remaining_tokens: int

    @property
    def is_healthy(self) -> bool:
        """Check if token usage is healthy (< 70 %)."""
        return self.usage_ratio < 0.70

    @property
    def needs_compression(self) -> bool:
        """Check if any compression is needed."""
        return self.compression_level != "none"

    @property
    def description(self) -> str:
        """Human-readable description of the current compression level."""
        return _COMPRESSION_DESCRIPTIONS.get(self.compression_level, "Unknown")

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "current_tokens": self.current_tokens,
            "max_tokens": self.max_tokens,
            "usage_ratio": round(self.usage_ratio, 4),
            "compression_level": self.compression_level,
            "is_over_budget": self.is_over_budget,
            "remaining_tokens": self.remaining_tokens,
            "is_healthy": self.is_healthy,
            "needs_compression": self.needs_compression,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# Component Budget Calculator
# ---------------------------------------------------------------------------

# Default allocation ratios for the available input budget.
# These are guidelines; a caller may override them.
_DEFAULT_COMPONENT_RATIOS: dict[str, float] = {
    "system_prompt": 0.10,
    "user_memory": 0.08,
    "cycle_briefing": 0.05,
    "recent_messages": 0.35,
    "tool_results": 0.12,
    "tool_definitions": 0.08,
    "workspace_refs": 0.07,
    "workspace_chunks": 0.10,
    "current_query": 0.05,
}

# Minimum absolute token guarantees per component
_COMPONENT_FLOOR: dict[str, int] = {
    "system_prompt": 200,
    "user_memory": 100,
    "cycle_briefing": 100,
    "recent_messages": 500,
    "tool_results": 200,
    "tool_definitions": 200,
    "workspace_refs": 100,
    "workspace_chunks": 100,
    "current_query": 50,
}


def calculate_token_budget(
    profile,
    model_capability,
    component_ratios: dict[str, float] | None = None,
) -> TokenBudget:
    """Calculate a complete TokenBudget from a profile and model capability.

    The calculation flow::

        1. safety_margin_tokens  = model.context_window * profile.safety_margin_ratio
        2. available_input_budget = model.context_window - output_reserved - safety_margin
        3. breakdown             = available_input_budget * component_ratios

    Args:
        profile: ContextProfile instance (must have safety_margin_ratio,
                 output_reserve_tokens, max_input_tokens).
        model_capability: ModelCapability instance (must have context_window).
        component_ratios: Optional override for per-component allocation ratios.
                         Keys missing from the override fall back to defaults.

    Returns:
        TokenBudget with full component breakdown.

    Raises:
        TypeError: If profile or model_capability have wrong types.
        ValueError: If computed available_input_budget is not positive.
    """
    # Deferred imports to avoid circularity at module load time
    from context.context_profile import ContextProfile
    from context.model_capability import ModelCapability as MC

    if not isinstance(profile, ContextProfile):
        raise TypeError(
            f"profile must be ContextProfile, got {type(profile).__name__}"
        )
    if not isinstance(model_capability, MC):
        raise TypeError(
            f"model_capability must be ModelCapability, got {type(model_capability).__name__}"
        )

    # 1. Determine effective context window
    context_window = model_capability.context_window

    # 2. Output reservation
    output_reserved = profile.output_reserve_tokens

    # 3. Safety margin
    safety_margin_tokens = int(context_window * profile.safety_margin_ratio)

    # 4. Available input budget
    available_input_budget = context_window - output_reserved - safety_margin_tokens

    if available_input_budget <= 0:
        # Emergency fallback: carve out a minimal budget
        logger.warning(
            "TokenBudget: computed available_input_budget <= 0; applying emergency fallback",
            extra={
                "context_window": context_window,
                "output_reserved": output_reserved,
                "safety_margin": safety_margin_tokens,
            },
        )
        available_input_budget = max(1024, int(context_window * 0.2))
        safety_margin_tokens = max(0, context_window - output_reserved - available_input_budget)

    # 5. Component breakdown
    ratios = dict(_DEFAULT_COMPONENT_RATIOS)
    if component_ratios:
        ratios.update(component_ratios)

    breakdown: dict[str, int] = {}
    for component, ratio in ratios.items():
        tokens = int(available_input_budget * ratio)
        floor = _COMPONENT_FLOOR.get(component, 0)
        breakdown[component] = max(floor, tokens)

    # Ensure breakdown does not exceed available budget (guard against rounding)
    total_breakdown = sum(breakdown.values())
    if total_breakdown > available_input_budget:
        # Trim proportionally from the largest component (recent_messages)
        excess = total_breakdown - available_input_budget
        if "recent_messages" in breakdown and breakdown["recent_messages"] > excess + 500:
            breakdown["recent_messages"] -= excess
        else:
            # Distribute trim across all components proportionally
            for component in breakdown:
                trim = int(excess * (breakdown[component] / total_breakdown))
                breakdown[component] = max(
                    _COMPONENT_FLOOR.get(component, 0),
                    breakdown[component] - trim,
                )

    return TokenBudget(
        context_window=context_window,
        output_reserved=output_reserved,
        safety_margin_tokens=safety_margin_tokens,
        available_input_budget=available_input_budget,
        breakdown=breakdown,
        used_tokens=0,
    )


# ---------------------------------------------------------------------------
# Standalone Utility Functions
# ---------------------------------------------------------------------------


def check_budget(total_tokens: int, max_tokens: int) -> BudgetStatus:
    """Check budget status from raw token counts.

    Standalone function for quick budget checks without creating
    a full TokenBudget instance.

    Args:
        total_tokens: Current token usage.
        max_tokens: Maximum allowed tokens.

    Returns:
        BudgetStatus with compression recommendation.

    Raises:
        ValueError: If max_tokens is not positive.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")

    ratio = total_tokens / max_tokens if max_tokens > 0 else 0.0

    return BudgetStatus(
        current_tokens=total_tokens,
        max_tokens=max_tokens,
        usage_ratio=ratio,
        compression_level="none",
        is_over_budget=ratio >= 1.0,
        remaining_tokens=max(0, max_tokens - total_tokens),
    )


def get_compression_level(usage_ratio: float) -> CompressionLevelName:
    """Compression is disabled."""
    return "none"


def get_compression_description(level: CompressionLevelName) -> str:
    """Get human-readable description for a compression level.

    Args:
        level: Compression level.

    Returns:
        Human-readable description.
    """
    return _COMPRESSION_DESCRIPTIONS.get(level, "Unknown compression level")


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses the conservative approximation: 1 token ~= 4 characters,
    matching the convention used throughout Context OS.

    Args:
        text: Text to estimate.

    Returns:
        Estimated token count (at least 1 for non-empty text).
    """
    if not text:
        return 0
    return max(1, len(str(text)) // 4)
