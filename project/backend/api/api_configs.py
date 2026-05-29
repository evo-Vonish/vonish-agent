"""API credential configuration routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import User, get_current_user
from core.config import settings
from core.secrets import decrypt_secret, encrypt_secret, mask_secret
from db.models import ApiProviderConfig
from db.session import get_db

router = APIRouter(prefix="/api")

Provider = Literal["deepseek", "kimi"]


def default_api_base(provider: str) -> str:
    if provider == "deepseek":
        return settings.deepseek_api_base
    if provider == "kimi":
        return settings.kimi_api_base
    return ""


class ApiConfigCreateRequest(BaseModel):
    provider: Provider
    name: str = Field(..., min_length=1, max_length=100)
    api_base: str = Field(default="", max_length=500)
    api_key: str = Field(..., min_length=1)
    is_default: bool = True


class ApiConfigUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    api_base: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None)
    is_default: bool | None = None


class ApiConfigResponse(BaseModel):
    id: str
    provider: str
    name: str
    api_base: str
    key_preview: str
    is_default: bool
    created_at: str
    updated_at: str


class ApiConfigListResponse(BaseModel):
    configs: list[ApiConfigResponse]
    total: int


def to_response(config: ApiProviderConfig) -> ApiConfigResponse:
    try:
        key_preview = mask_secret(decrypt_secret(config.api_key_encrypted))
    except Exception:
        key_preview = "********"

    created_at = config.created_at or datetime.now(timezone.utc)
    updated_at = config.updated_at or created_at
    return ApiConfigResponse(
        id=str(config.id),
        provider=config.provider,
        name=config.name,
        api_base=config.api_base,
        key_preview=key_preview,
        is_default=config.is_default,
        created_at=created_at.isoformat(),
        updated_at=updated_at.isoformat(),
    )


async def ensure_single_default(
    db: AsyncSession,
    user_id: str,
    provider: str,
    keep_id: UUID,
) -> None:
    await db.execute(
        update(ApiProviderConfig)
        .where(
            ApiProviderConfig.user_id == user_id,
            ApiProviderConfig.provider == provider,
            ApiProviderConfig.id != keep_id,
        )
        .values(is_default=False)
    )


@router.get("/api-configs", response_model=ApiConfigListResponse)
async def list_api_configs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(ApiProviderConfig)
        .where(ApiProviderConfig.user_id == user.id)
        .order_by(ApiProviderConfig.provider.asc(), ApiProviderConfig.created_at.desc())
    )
    configs = list((await db.execute(stmt)).scalars().all())
    return ApiConfigListResponse(
        configs=[to_response(config) for config in configs],
        total=len(configs),
    )


@router.post("/api-configs", response_model=ApiConfigResponse)
async def create_api_config(
    request: ApiConfigCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = ApiProviderConfig(
        user_id=user.id,
        provider=request.provider,
        name=request.name.strip(),
        api_base=(request.api_base or default_api_base(request.provider)).rstrip("/"),
        api_key_encrypted=encrypt_secret(request.api_key),
        is_default=request.is_default,
    )
    db.add(config)
    await db.flush()

    if config.is_default:
        await ensure_single_default(db, user.id, config.provider, config.id)

    await db.commit()
    await db.refresh(config)
    return to_response(config)


@router.patch("/api-configs/{config_id}", response_model=ApiConfigResponse)
async def update_api_config(
    config_id: str,
    request: ApiConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = await db.get(ApiProviderConfig, UUID(config_id))
    if config is None or config.user_id != user.id:
        raise HTTPException(status_code=404, detail="API config not found")

    if request.name is not None:
        config.name = request.name.strip()
    if request.api_base is not None:
        config.api_base = (request.api_base or default_api_base(config.provider)).rstrip("/")
    if request.api_key is not None and request.api_key.strip():
        config.api_key_encrypted = encrypt_secret(request.api_key)
    if request.is_default is not None:
        config.is_default = request.is_default

    if config.is_default:
        await ensure_single_default(db, user.id, config.provider, config.id)

    await db.commit()
    await db.refresh(config)
    return to_response(config)


@router.post("/api-configs/{config_id}/default", response_model=ApiConfigResponse)
async def set_default_api_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = await db.get(ApiProviderConfig, UUID(config_id))
    if config is None or config.user_id != user.id:
        raise HTTPException(status_code=404, detail="API config not found")

    config.is_default = True
    await ensure_single_default(db, user.id, config.provider, config.id)
    await db.commit()
    await db.refresh(config)
    return to_response(config)


@router.delete("/api-configs/{config_id}")
async def delete_api_config(
    config_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    config = await db.get(ApiProviderConfig, UUID(config_id))
    if config is None or config.user_id != user.id:
        raise HTTPException(status_code=404, detail="API config not found")

    await db.delete(config)
    await db.commit()
    return {"status": "deleted", "id": config_id}
