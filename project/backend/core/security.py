"""Security utilities for the Agent system."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Any


# ---------------------------------------------------------------------------
# Password & Token Utilities
# ---------------------------------------------------------------------------

def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Hash a password with a salt (placeholder implementation).

    Future: Use bcrypt or argon2 for production.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return key.hex(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Verify a password against its hash."""
    key, _ = hash_password(password, salt)
    return hmac.compare_digest(key, hashed)


# ---------------------------------------------------------------------------
# Input Sanitization
# ---------------------------------------------------------------------------

def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal and injection.

    Args:
        filename: Raw filename string.

    Returns:
        Sanitized filename.
    """
    # Remove path separators and null bytes
    sanitized = re.sub(r'[\\/<>|":?*\x00-\x1f]', "_", filename)
    # Prevent leading dots (hidden files)
    sanitized = sanitized.lstrip(".")
    # Limit length
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[:255 - len(ext)] + ext
    return sanitized or "unnamed"


def sanitize_path_component(component: str) -> str:
    """Sanitize a single path component.

    Args:
        component: Path component string.

    Returns:
        Sanitized component.
    """
    component = component.replace("..", "_")
    component = component.replace("//", "_")
    component = component.strip("/")
    return component or "_"


# ---------------------------------------------------------------------------
# Content Security
# ---------------------------------------------------------------------------

ALLOWED_MIME_TYPES = {
    # Documents
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    # Images (for vision models)
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    # Code files
    "text/x-python",
    "text/javascript",
    "text/html",
    "text/css",
    "application/xml",
}

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def validate_mime_type(mime_type: str) -> bool:
    """Check if a MIME type is in the allowed list.

    Args:
        mime_type: MIME type string.

    Returns:
        True if allowed, False otherwise.
    """
    return mime_type in ALLOWED_MIME_TYPES


def validate_file_size(size: int) -> bool:
    """Check if file size is within allowed limit.

    Args:
        size: File size in bytes.

    Returns:
        True if within limit, False otherwise.
    """
    return 0 < size <= MAX_UPLOAD_SIZE


def generate_resource_uri(
    resource_type: str,
    conversation_id: str,
    filename: str,
) -> str:
    """Generate a unique resource URI.

    Args:
        resource_type: Type of resource (upload, tool_output, crawl_result).
        conversation_id: Conversation identifier.
        filename: File name.

    Returns:
        Resource URI string.
    """
    safe_name = sanitize_filename(filename)
    return f"resource://workspace/{conversation_id}/{resource_type}/{safe_name}"


# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------

def get_cors_origins() -> list[str]:
    """Get allowed CORS origins."""
    env_origins = os.environ.get("CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://localhost:18473",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:18473",
    ]
