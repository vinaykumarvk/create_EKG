"""Session helpers."""
from __future__ import annotations

from typing import Any, Dict

try:
    from fastapi import Request  # type: ignore
except Exception:  # pragma: no cover - fallback for tests
    class Request(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.session = {}

ADMIN_SESSION_KEY = "admin_authenticated"
CSRF_SESSION_KEY = "csrf_token"


def is_authenticated(request: Request) -> bool:
    """Return ``True`` when the current session belongs to the admin."""

    return bool(request.session.get(ADMIN_SESSION_KEY))


def login_admin(request: Request) -> None:
    """Mark the current session as authenticated."""

    request.session[ADMIN_SESSION_KEY] = True


def logout_admin(request: Request) -> None:
    """Remove the admin authentication marker."""

    request.session.pop(ADMIN_SESSION_KEY, None)


def get_csrf_token(request: Request) -> str:
    """Return the CSRF token for this session, creating one if necessary."""

    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        from .security import generate_csrf_token

        token = generate_csrf_token()
        request.session[CSRF_SESSION_KEY] = token
    return token


def clear_csrf_token(request: Request) -> None:
    """Remove the CSRF token from the session."""

    request.session.pop(CSRF_SESSION_KEY, None)


def flash_message(request: Request, message: str, category: str = "info") -> None:
    """Store a single flash message for the next request."""

    request.session["flash"] = {"message": message, "category": category}


def consume_flash(request: Request) -> Dict[str, Any]:
    """Return and clear any previously stored flash message."""

    return request.session.pop("flash", {})
