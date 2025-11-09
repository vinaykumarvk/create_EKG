import io

import pytest
from api.compat import UploadFile

from api.google_drive import extract_folder_id
from api.security import hash_password, verify_password
from api.vector_store import MAX_FILE_BYTES, ensure_file_size, validate_upload


def test_extract_folder_id_from_url():
    folder = extract_folder_id("https://drive.google.com/drive/folders/1AbCdEfGhIJ")
    assert folder == "1AbCdEfGhIJ"


def test_hash_and_verify_password():
    hashed = hash_password("super-secure-password")
    assert verify_password("super-secure-password", hashed)
    assert not verify_password("wrong", hashed)


def test_validate_upload_rejects_unknown_extension():
    upload = UploadFile(filename="malicious.exe", file=io.BytesIO(b"data"))
    with pytest.raises(Exception):
        validate_upload(upload)


def test_ensure_file_size_limits():
    ensure_file_size(b"hello")
    with pytest.raises(Exception):
        ensure_file_size(b"x" * (MAX_FILE_BYTES + 1))
