"""Integration with OpenAI vector stores."""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from .compat import HTTPException, UploadFile, status

try:  # Optional import; tests can mock when not available
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency may be missing
    OpenAI = None  # type: ignore

from .settings import settings

LOGGER = logging.getLogger(__name__)

MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".csv", ".json"}


def _assert_openai_client() -> "OpenAI":
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key is not configured.",
        )
    if OpenAI is None:  # pragma: no cover - import guard
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI client library is not installed.",
        )
    return OpenAI(api_key=settings.openai_api_key)


def validate_upload(file: UploadFile) -> None:
    """Validate the uploaded file before processing."""

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename cannot be blank.")

    extension = Path(file.filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {extension}",
        )


def ensure_file_size(content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file exceeds the 100 MB limit.",
        )


def _ensure_vector_store(client: "OpenAI") -> str:
    if settings.openai_vector_store_id:
        return settings.openai_vector_store_id

    response = client.beta.vector_stores.create(name=settings.openai_vector_store_name)
    vector_store_id = response.id
    os.environ.setdefault("OPENAI_VECTOR_STORE_ID", vector_store_id)
    return vector_store_id


def _find_existing_file_id(client: "OpenAI", vector_store_id: str, filename: str) -> Optional[str]:
    files = client.beta.vector_stores.files.list(vector_store_id=vector_store_id)
    for file_obj in files.data:
        try:
            file_details = client.files.retrieve(file_obj.id)
        except Exception:  # pragma: no cover - network failure
            LOGGER.exception("Unable to retrieve file details for %s", file_obj.id)
            continue
        if file_details.filename == filename:
            return file_obj.id
    return None


def _delete_file(client: "OpenAI", vector_store_id: str, file_id: str) -> None:
    try:
        client.beta.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
    except Exception as exc:  # pragma: no cover - deletion may fail
        LOGGER.warning("Failed to delete file %s from vector store: %s", file_id, exc)


def ingest_file(file: UploadFile) -> dict:
    """Upload a file to the OpenAI vector store, replacing previous versions."""

    validate_upload(file)
    content = file.file.read()
    ensure_file_size(content)

    client = _assert_openai_client()
    vector_store_id = _ensure_vector_store(client)

    existing_file_id = _find_existing_file_id(client, vector_store_id, file.filename)
    if existing_file_id:
        _delete_file(client, vector_store_id, existing_file_id)

    with tempfile.NamedTemporaryFile(delete=False) as temp:
        temp.write(content)
        temp_path = Path(temp.name)

    try:
        with temp_path.open("rb") as handle:
            response = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store_id,
                files=[handle],
            )
    finally:
        temp_path.unlink(missing_ok=True)

    return {
        "vector_store_id": vector_store_id,
        "file_count": response.file_counts,  # type: ignore[attr-defined]
        "status": getattr(response, "status", "completed"),
    }
