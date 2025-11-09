"""Compatibility helpers so tests run without optional FastAPI dependency."""
from __future__ import annotations

from dataclasses import dataclass
from typing import IO, Optional

try:  # pragma: no cover - real FastAPI available
    from fastapi import HTTPException  # type: ignore
    from fastapi import status as fastapi_status  # type: ignore
    from fastapi import UploadFile  # type: ignore

    HTTPException = HTTPException
    status = fastapi_status
    UploadFile = UploadFile
except Exception:  # pragma: no cover - fallback implementations

    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Optional[str] = None):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _StatusModule:
        HTTP_303_SEE_OTHER = 303
        HTTP_400_BAD_REQUEST = 400
        HTTP_401_UNAUTHORIZED = 401
        HTTP_503_SERVICE_UNAVAILABLE = 503

    status = _StatusModule()

    @dataclass
    class UploadFile:  # type: ignore
        filename: Optional[str] = None
        file: Optional[IO[bytes]] = None

        def __post_init__(self) -> None:
            if self.file is None:
                import io

                self.file = io.BytesIO()

        async def read(self) -> bytes:
            return self.file.read() if self.file else b""
