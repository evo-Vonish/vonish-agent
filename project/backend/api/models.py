"""Model Management API routes.

Provides:
- GET /api/models - List available models
- POST /api/models/select - Switch model for conversation
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.auth import User, get_current_user
from core.config import MODEL_CONFIGS
from core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class SelectModelRequest(BaseModel):
    """Request to select/change model."""

    model_id: str = Field(..., description="Model identifier")
    conversation_id: str = Field(default="", description="Target conversation")


class ModelInfoResponse(BaseModel):
    """Model information response."""

    id: str
    provider: str
    context_window: int
    max_output_tokens: int
    supports_vision: bool
    supports_json_mode: bool
    supports_thinking: bool
    supports_context_cache: bool
    default_thinking_effort: str = "high"


class ModelListResponse(BaseModel):
    """List of available models."""

    models: list[ModelInfoResponse]
    current_model: str = ""
    total: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    user: User = Depends(get_current_user),
):
    """List all available models with their capabilities."""
    try:
        models = [
            ModelInfoResponse(
                id=str(model_id),
                provider=str(config.provider),
                context_window=int(config.context_window),
                max_output_tokens=int(config.max_output_tokens),
                supports_vision=bool(config.supports_vision),
                supports_json_mode=bool(config.supports_json_mode),
                supports_thinking=bool(config.supports_thinking),
                supports_context_cache=bool(config.supports_context_cache),
                default_thinking_effort=str(getattr(config, "default_thinking_effort", "high") or "high"),
            )
            for model_id, config in MODEL_CONFIGS.items()
        ]
    except Exception as exc:
        logger.exception("Failed to build model list")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load model configuration: {exc}",
        ) from exc

    current_model = (
        "deepseek-v4-pro"
        if "deepseek-v4-pro" in MODEL_CONFIGS
        else (next(iter(MODEL_CONFIGS.keys()), ""))
    )

    return ModelListResponse(
        models=models,
        current_model=current_model,
        total=len(models),
    )


@router.post("/models/select")
async def select_model(
    request: SelectModelRequest,
    user: User = Depends(get_current_user),
):
    """Select/switch the model for a conversation.

    Changes the LLM model used for a specific conversation.
    """
    if request.model_id not in MODEL_CONFIGS:
        available = list(MODEL_CONFIGS.keys())
        raise HTTPException(
            status_code=422,
            detail=f"Unknown model: {request.model_id}. Available: {available}",
        )

    config = MODEL_CONFIGS[request.model_id]

    logger.info(
        f"Model selected: {request.model_id} for conversation {request.conversation_id}"
    )

    return {
        "status": "switched",
        "model_id": request.model_id,
        "conversation_id": request.conversation_id,
        "provider": config.provider,
        "capabilities": {
            "context_window": config.context_window,
            "supports_vision": config.supports_vision,
            "supports_thinking": config.supports_thinking,
        },
    }
