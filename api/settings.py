"""Application settings management without external dependencies."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    app_name: str = "Create EKG Admin"
    session_secret: str = os.getenv("SESSION_SECRET", "change-me-please-32-characters")
    admin_username: str = os.getenv("ADMIN_USERNAME", "admin")
    admin_password_hash: Optional[str] = os.getenv("ADMIN_PASSWORD_HASH")
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    openai_vector_store_id: Optional[str] = os.getenv("OPENAI_VECTOR_STORE_ID")
    openai_vector_store_name: str = os.getenv(
        "OPENAI_VECTOR_STORE_NAME", "Create EKG Vector Store"
    )
    google_service_account_file: Optional[Path] = (
        Path(path) if (path := os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")) else None
    )
    google_impersonated_user: Optional[str] = os.getenv("GOOGLE_IMPERSONATED_USER")

    def __post_init__(self) -> None:
        if len(self.session_secret) < 16:
            raise ValueError("SESSION_SECRET must be at least 16 characters long")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
