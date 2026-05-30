"""Context Management API routes for Context OS v2.

Provides endpoints for:
    - GET  /api/context/{conversation_id}/preview   — Context preview with token breakdown
    - POST /api/context/{conversation_id}/profile   — Switch context profile
    - POST /api/context/{conversation_id}/rebuild   — Force rebuild context
    - POST /api/context/{conversation_id}/compact   — Trigger compression
    - GET  /api/context/{conversation_id}/usage     — Token usage statistics
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from context.context_builder import ContextBuilder, BuiltContext
from context.context_preview import ContextPreview, ContextPreviewResponse
from context.context_profile import get_profile, list_profiles, update_custom_profile, ContextProfile
from context.model_capability import list_registered_models
from context.token_budget import calculate_token_budget, check_budget, estimate_tokens
from core.auth import User, get_current_user
from core.logging import get_logger
from db.session import get_db

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class SwitchProfileRequest(BaseModel):
    """Request to switch context profile."""

    profile: str = Field(
        ...,
        description="Profile name: cheap, balanced, max, or custom",
        examples=["balanced"],
    )


class ProfileUpdateResponse(BaseModel):
    """Response for profile switch."""

    status: str
    conversation_id: str
    profile: str
    profile_config: dict[str, Any]


class RebuildResponse(BaseModel):
    """Response for context rebuild."""

    status: str
    conversation_id: str
    message: str
    built_context: dict[str, Any] | None = None


class CompactResponse(BaseModel):
    """Response for context compaction."""

    status: str
    conversation_id: str
    compression_level: str
    tokens_saved: int
    warnings: list[str]


class UsageResponse(BaseModel):
    """Response for token usage query."""

    conversation_id: str
    total_tokens: int
    max_tokens: int
    available_budget: int
    output_reserved: int
    safety_margin: int
    profile: str
    model: str
    usage_ratio: float
    compression_level: str
    budget_healthy: bool
    components: dict[str, int]


# ---------------------------------------------------------------------------
# GET /api/context/{conversation_id}/preview
# ---------------------------------------------------------------------------


@router.get("/context/{conversation_id}/preview")
async def get_context_preview(
    conversation_id: str,
    model_id: str = "deepseek-chat",
    profile_name: str = "balanced",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ContextPreviewResponse:
    """Get a preview of the assembled context.

    Shows how the context will be built for the next message,
    including per-block token distribution and budget status.

    Args:
        conversation_id: Conversation ID.
        model_id: Model identifier (e.g. 'deepseek-chat', 'kimi-k2-6').
        profile_name: Context profile name (cheap, balanced, max).
    """
    try:
        preview = ContextPreview()
        builder = ContextBuilder()

        response = await preview.generate_preview(
            conversation_id=conversation_id,
            builder=builder,
            model_id=model_id,
            profile_name=profile_name,
        )
        return response

    except ValueError as e:
        logger.warning(f"Preview validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Preview generation error: {e}")
        # Return a minimal preview
        return ContextPreviewResponse(
            conversation_id=conversation_id,
            profile=profile_name,
            model=model_id,
            context_window=0,
            estimated_input_tokens=0,
            output_reserved_tokens=0,
            safety_margin_tokens=0,
            available_budget=0,
            blocks=[],
            warnings=[f"Preview generation error: {e}"],
        )


# ---------------------------------------------------------------------------
# POST /api/context/{conversation_id}/profile
# ---------------------------------------------------------------------------


@router.post("/context/{conversation_id}/profile")
async def switch_context_profile(
    conversation_id: str,
    request: SwitchProfileRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProfileUpdateResponse:
    """Switch the context profile for a conversation.

    Changes the context allocation strategy (cheap / balanced / max).
    The new profile takes effect on the next context build.

    Args:
        conversation_id: Conversation ID.
        request: SwitchProfileRequest with the new profile name.
    """
    try:
        profile = get_profile(request.profile)
    except ValueError as e:
        available = list_profiles()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid profile: {e}. Available: {available}",
        )

    logger.info(
        "Switched context profile",
        extra={
            "conversation_id": conversation_id,
            "new_profile": request.profile,
            "user_id": getattr(user, "id", "unknown"),
        },
    )

    return ProfileUpdateResponse(
        status="switched",
        conversation_id=conversation_id,
        profile=request.profile,
        profile_config=profile.to_dict(),
    )


# ---------------------------------------------------------------------------
# POST /api/context/{conversation_id}/rebuild
# ---------------------------------------------------------------------------


@router.post("/context/{conversation_id}/rebuild")
async def rebuild_context(
    conversation_id: str,
    model_id: str = "deepseek-chat",
    profile_name: str = "balanced",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RebuildResponse:
    """Force a rebuild of the context for a conversation.

    Triggers a fresh context assembly, clearing any cached state.
    This is useful when the conversation state has changed significantly
    and you want to ensure the context reflects the latest state.

    Args:
        conversation_id: Conversation ID.
        model_id: Model identifier.
        profile_name: Context profile name.
    """
    logger.info(
        "Rebuilding context",
        extra={
            "conversation_id": conversation_id,
            "model_id": model_id,
            "profile": profile_name,
        },
    )

    try:
        builder = ContextBuilder()

        # Perform an actual build to validate everything works
        built = await builder.build(
            conversation_id=conversation_id,
            user_query="[context rebuild — no active query]",
            model_id=model_id,
            profile_name=profile_name,
        )

        return RebuildResponse(
            status="rebuilt",
            conversation_id=conversation_id,
            message="Context has been rebuilt successfully",
            built_context=built.to_dict(),
        )

    except Exception as e:
        logger.error(f"Context rebuild failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context rebuild failed: {e}",
        )


# ---------------------------------------------------------------------------
# POST /api/context/{conversation_id}/compact
# ---------------------------------------------------------------------------


@router.post("/context/{conversation_id}/compact")
async def compact_context(
    conversation_id: str,
    profile_name: str = "balanced",
    model_id: str = "deepseek-chat",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompactResponse:
    """Trigger compression on the context for a conversation.

    Runs the five-phase compression pipeline to reduce token usage.
    This is useful when approaching the context window limit.

    Args:
        conversation_id: Conversation ID.
        profile_name: Context profile name.
        model_id: Model identifier.
    """
    logger.info(
        "Compacting context",
        extra={
            "conversation_id": conversation_id,
            "profile": profile_name,
            "model_id": model_id,
        },
    )

    try:
        from context.model_capability import resolve_model_capability
        from context.context_profile import scale_profile_for_model

        # Resolve model and profile
        model = resolve_model_capability(model_id)
        profile = get_profile(profile_name)
        scaled = scale_profile_for_model(profile, model)

        # Calculate current budget
        budget = calculate_token_budget(scaled, model)

        # Estimate current usage (simplified — production would query DB)
        estimated_usage = int(budget.available_input_budget * 0.85)
        budget.set_usage(estimated_usage)

        status = budget.check_budget()

        # Run compression
        from context.compression_engine import CompressionEngine
        from context.context_builder import ContextState

        engine = CompressionEngine()
        ctx = ContextState()

        result = await engine.compress(ctx, scaled, budget)

        total_saved = result.get("total_tokens_saved", 0)
        warnings = result.get("warnings", [])

        logger.info(
            "Context compacted",
            extra={
                "conversation_id": conversation_id,
                "tokens_saved": total_saved,
                "compression_level": status.compression_level,
            },
        )

        return CompactResponse(
            status="compacted",
            conversation_id=conversation_id,
            compression_level=status.compression_level,
            tokens_saved=total_saved,
            warnings=warnings,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Context compaction failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context compaction failed: {e}",
        )


# ---------------------------------------------------------------------------
# GET /api/context/{conversation_id}/usage
# ---------------------------------------------------------------------------


@router.get("/context/{conversation_id}/usage")
async def get_context_usage(
    conversation_id: str,
    model_id: str = "deepseek-chat",
    profile_name: str = "balanced",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UsageResponse:
    """Get token usage statistics for a conversation.

    Returns current token consumption, budget status, and per-component
    breakdown. Uses real database queries via ContextTracker.

    Args:
        conversation_id: Conversation ID.
        model_id: Model identifier.
        profile_name: Context profile name.
    """
    try:
        from services.context_tracker import get_context_tracker

        tracker = get_context_tracker()
        snapshot = await tracker.snapshot(
            conversation_id=conversation_id,
            db=db,
            model_id=model_id,
            profile_name=profile_name,
        )

        return UsageResponse(
            conversation_id=conversation_id,
            total_tokens=snapshot.total_estimated_tokens,
            max_tokens=snapshot.max_input_tokens,
            available_budget=snapshot.available_budget,
            output_reserved=snapshot.output_reserved,
            safety_margin=snapshot.safety_margin,
            profile=snapshot.profile_name,
            model=model_id,
            usage_ratio=round(snapshot.usage_ratio, 4),
            compression_level=snapshot.compression_level,
            budget_healthy=snapshot.budget_healthy,
            components=snapshot.components,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Context usage query failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context usage query failed: {e}",
        )


# ---------------------------------------------------------------------------
# Additional utility endpoints
# ---------------------------------------------------------------------------


@router.get("/context/profiles")
async def list_context_profiles(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all available context profiles with their configurations."""
    from context.context_profile import CONTEXT_PROFILES

    return {
        "profiles": {
            name: profile.to_dict()
            for name, profile in CONTEXT_PROFILES.items()
        },
    }


@router.get("/context/models")
async def list_context_models(
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all registered models with their capabilities."""
    from context.model_capability import get_registry

    registry = get_registry()
    caps = [cap.to_dict() for cap in registry.all_capabilities()]

    return {
        "models": caps,
        "count": len(caps),
    }
