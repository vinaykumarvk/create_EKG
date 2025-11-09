"""Helpers for interacting with Google Drive."""
from __future__ import annotations

import re
from typing import Iterable, List, Optional

from .compat import HTTPException, status

try:  # Optional dependency
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception:  # pragma: no cover - optional dependency may be missing
    service_account = None  # type: ignore
    build = None  # type: ignore

FOLDER_ID_PATTERN = re.compile(r"[-\w]{10,}")


class GoogleDriveClient:
    """Thin wrapper around the Google Drive API."""

    def __init__(self, credentials_file: Optional[str], impersonated_user: Optional[str]):
        if not credentials_file or not service_account or not build:
            self._client = None
            return

        scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=scopes
        )
        if impersonated_user:
            credentials = credentials.with_subject(impersonated_user)
        self._client = build("drive", "v3", credentials=credentials, cache_discovery=False)

    @property
    def enabled(self) -> bool:
        """Return ``True`` if the Drive client is ready for use."""

        return self._client is not None

    def list_folder(self, folder_id: str) -> List[dict]:
        """Return the files available inside ``folder_id``."""

        if not self._client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Drive integration is not configured.",
            )

        fields = "files(id, name, mimeType, size, modifiedTime)"
        query = f"'{folder_id}' in parents and trashed = false"
        result = (
            self._client.files()
            .list(q=query, fields=fields, pageSize=1000, supportsAllDrives=True)
            .execute()
        )
        return result.get("files", [])

    def download_file(self, file_id: str) -> bytes:
        """Download ``file_id`` from Google Drive."""

        if not self._client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google Drive integration is not configured.",
            )

        request = self._client.files().get_media(fileId=file_id)
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore
        import io

        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.seek(0)
        return fh.read()


def extract_folder_id(folder_link: str) -> Optional[str]:
    """Extract the Drive folder ID from a URL or plain ID string."""

    if not folder_link:
        return None

    if FOLDER_ID_PATTERN.fullmatch(folder_link):
        return folder_link

    match = FOLDER_ID_PATTERN.search(folder_link)
    if match:
        return match.group(0)
    return None


def validate_drive_file_size(size: Optional[str], max_bytes: int) -> None:
    """Ensure the remote file is within the allowed size limit."""

    if not size:
        return
    try:
        if int(size) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google Drive file exceeds the maximum allowed size.",
            )
    except ValueError:
        return


def select_best_file(files: Iterable[dict]) -> Optional[dict]:
    """Pick the most recently modified file from the iterable."""

    return max(files, key=lambda f: f.get("modifiedTime", ""), default=None)
