"""JWT Authentication placeholder.

Current stage: all requests pass through with a mock user.
The authentication middleware structure is preserved for future implementation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ---------------------------------------------------------------------------
# Mock User & Auth Models
# ---------------------------------------------------------------------------

class User(BaseModel):
    """Authenticated user model."""

    id: str = "mock-user-001"
    username: str = "developer"
    email: str = "dev@example.com"
    avatar_url: str = ""
    preferences: dict[str, Any] = Field(default_factory=dict)
    is_authenticated: bool = True


# ---------------------------------------------------------------------------
# JWT Token Utilities (placeholder structure)
# ---------------------------------------------------------------------------

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    """Dependency: get the current authenticated user.

    Current stage: Returns a mock user for all requests.
    Future: Will validate JWT token and look up user from database.

    Args:
        credentials: Bearer token from Authorization header.

    Returns:
        User instance (mock user in current stage).
    """
    # Future implementation:
    # if not credentials:
    #     raise HTTPException(status_code=401, detail="Missing authentication token")
    # token = credentials.credentials
    # payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    # user = await get_user_from_db(payload["sub"])
    # return user

    return User(
        id="mock-user-001",
        username="developer",
        email="dev@example.com",
    )


async def optional_user(
    request: Request,
) -> User | None:
    """Optional dependency: get user if authenticated, else None."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return await get_current_user()
    return None


# ---------------------------------------------------------------------------
# JWT Token Generation (for future use)
# ---------------------------------------------------------------------------

def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
    secret_key: str = "dev-secret-key",
) -> str:
    """Create a JWT access token (placeholder).

    Args:
        user_id: User identifier.
        expires_delta: Token expiration time.
        secret_key: Secret key for signing.

    Returns:
        JWT token string.
    """
    # from jose import jwt
    # to_encode = {"sub": user_id, "iat": datetime.now(timezone.utc)}
    # if expires_delta:
    #     to_encode["exp"] = datetime.now(timezone.utc) + expires_delta
    # else:
    #     to_encode["exp"] = datetime.now(timezone.utc) + timedelta(minutes=15)
    # return jwt.encode(to_encode, secret_key, algorithm="HS256")
    return f"mock-token-{user_id}"
