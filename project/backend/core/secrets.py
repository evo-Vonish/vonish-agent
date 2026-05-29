"""Secret encryption helpers for persisted backend credentials."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    """Encrypt a secret for database storage."""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """Decrypt a database-stored secret."""
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: str) -> str:
    """Return a non-sensitive display version of a secret."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"
