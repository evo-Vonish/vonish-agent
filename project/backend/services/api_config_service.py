"""API provider configuration lookup helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.secrets import decrypt_secret
from db.models import ApiProviderConfig


@dataclass(frozen=True)
class ResolvedApiConfig:
    provider: str
    name: str
    api_base: str
    api_key: str


async def get_default_api_config(
    db: AsyncSession,
    user_id: str,
    provider: str,
) -> ResolvedApiConfig | None:
    """Return the user's default config for a provider, or the newest one."""
    stmt = (
        select(ApiProviderConfig)
        .where(
            ApiProviderConfig.user_id == user_id,
            ApiProviderConfig.provider == provider,
        )
        .order_by(ApiProviderConfig.is_default.desc(), ApiProviderConfig.created_at.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        return None

    return ResolvedApiConfig(
        provider=row.provider,
        name=row.name,
        api_base=row.api_base,
        api_key=decrypt_secret(row.api_key_encrypted),
    )
