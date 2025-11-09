"""Security helpers for authentication and CSRF protection."""
from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Optional

from .compat import HTTPException, status

PBKDF2_ROUNDS = 390000


def _pbkdf2(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)


def hash_password(password: str) -> str:
    """Create a deterministic PBKDF2 hash for the provided password."""

    salt = secrets.token_bytes(16)
    dk = _pbkdf2(password, salt)
    return "pbkdf2$" + base64.b64encode(salt + dk).decode()


def _split_hash(hashed: str) -> Optional[tuple[bytes, bytes]]:
    if not hashed or not hashed.startswith("pbkdf2$"):
        return None
    try:
        raw = base64.b64decode(hashed.split("$", 1)[1])
    except Exception:
        return None
    return raw[:16], raw[16:]


def verify_password(password: str, hashed: Optional[str]) -> bool:
    """Check whether ``password`` matches the stored ``hashed`` value."""

    parts = _split_hash(hashed or "")
    if not parts:
        return False
    salt, digest = parts
    candidate = _pbkdf2(password, salt)
    return secrets.compare_digest(candidate, digest)


def require_admin_password(password: str, hashed: Optional[str]) -> None:
    """Raise an :class:`HTTPException` if the admin password is invalid."""

    if not verify_password(password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )


def generate_csrf_token() -> str:
    """Return a random CSRF token."""

    return secrets.token_urlsafe(32)


def validate_csrf_token(session_token: Optional[str], form_token: Optional[str]) -> None:
    """Ensure the provided CSRF tokens match and raise if they do not."""

    if not session_token or not form_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing CSRF token",
        )
    if not secrets.compare_digest(session_token, form_token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CSRF token",
        )
