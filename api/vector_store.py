"""Integration with OpenAI vector stores."""
from __future__ import annotations

import io
import logging
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
CONVERTIBLE_EXTENSIONS = {".xlsx"}  # Files that need conversion before upload


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
    if extension not in SUPPORTED_EXTENSIONS and extension not in CONVERTIBLE_EXTENSIONS:
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


def _ensure_vector_store(client: "OpenAI", vector_store_id: Optional[str] = None) -> str:
    """Ensure a vector store exists. If vector_store_id is provided, use it. Otherwise use default from settings."""
    if vector_store_id:
        # Verify the vector store exists
        try:
            client.vector_stores.retrieve(vector_store_id)
            return vector_store_id
        except Exception as e:
            LOGGER.warning("Vector store %s not found: %s. Will create new one or use default.", vector_store_id, e)
            # If the specified vector store doesn't exist, fall through to default handling
            vector_store_id = None
    
    # Try to use default from settings, but verify it exists
    if settings.openai_vector_store_id:
        try:
            client.vector_stores.retrieve(settings.openai_vector_store_id)
            return settings.openai_vector_store_id
        except Exception as e:
            LOGGER.warning("Default vector store %s not found: %s. Will create new one.", settings.openai_vector_store_id, e)
            # Default vector store doesn't exist, create a new one

    # Create a new vector store
    response = client.vector_stores.create(name=settings.openai_vector_store_name)
    vector_store_id = response.id
    LOGGER.info("Created new vector store: %s (ID: %s)", settings.openai_vector_store_name, vector_store_id)
    # Configuration is supplied via settings/env, so we intentionally avoid mutating environment variables here.
    return vector_store_id


def list_vector_stores(client: Optional["OpenAI"] = None) -> list[dict]:
    """List all vector stores available in OpenAI."""
    if client is None:
        client = _assert_openai_client()
    
    try:
        response = client.vector_stores.list()
        stores = []
        for vs in response.data:
            stores.append({
                "id": vs.id,
                "name": getattr(vs, "name", "Unnamed"),
                "file_count": getattr(vs.file_counts, "total", 0) if hasattr(vs, "file_counts") else 0,
                "created_at": getattr(vs, "created_at", None),
            })
        return stores
    except Exception as e:
        LOGGER.exception("Error listing vector stores: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list vector stores: {str(e)}"
        )


def create_vector_store(name: str, client: Optional["OpenAI"] = None) -> dict:
    """Create a new vector store with the given name (domain)."""
    if client is None:
        client = _assert_openai_client()
    
    if not name or not name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vector store name cannot be empty."
        )
    
    try:
        response = client.vector_stores.create(name=name.strip())
        return {
            "id": response.id,
            "name": getattr(response, "name", name.strip()),
            "file_count": 0,
            "created_at": getattr(response, "created_at", None),
        }
    except Exception as e:
        LOGGER.exception("Error creating vector store: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create vector store: {str(e)}"
        )


def list_vector_store_files(vector_store_id: str, client: Optional["OpenAI"] = None) -> list[dict]:
    """List all files in a vector store, paginating through all results."""
    if client is None:
        client = _assert_openai_client()
    
    try:
        files = []
        # Paginate through all results
        # OpenAI API returns paginated results, so we need to fetch all pages
        after = None
        limit = 100  # Maximum allowed by OpenAI API
        
        while True:
            # Fetch a page of results
            params = {"vector_store_id": vector_store_id, "limit": limit}
            if after:
                params["after"] = after
            
            files_response = client.vector_stores.files.list(**params)
            
            # If no data in this page, we're done
            if not files_response.data:
                break
            
            # Process files in this page
            for file_obj in files_response.data:
                status = getattr(file_obj, "status", None)
                if status and status.lower() in {"deleted", "not_found"}:
                    LOGGER.info(
                        "Skipping file %s in vector store %s with status %s",
                        file_obj.id,
                        vector_store_id,
                        status,
                    )
                    continue

                try:
                    file_details = client.files.retrieve(file_obj.id)
                except Exception as e:
                    LOGGER.warning(
                        "Unable to retrieve file details for %s (likely deleted): %s",
                        file_obj.id,
                        e,
                    )
                    # Skip entries we cannot retrieve; they are likely fully deleted
                    continue

                filename = getattr(file_obj, "filename", None) or getattr(
                    file_details, "filename", None
                ) or file_obj.id

                files.append(
                    {
                        "id": file_obj.id,
                        "filename": filename,
                        "status": status or getattr(file_details, "status", "unknown"),
                        "created_at": getattr(file_details, "created_at", None),
                        "bytes": getattr(file_details, "bytes", 0),
                    }
                )
            
            # Check if there are more pages
            # OpenAI API may use 'has_more' flag, or we check if we got a full page
            has_more = getattr(files_response, "has_more", None)
            if has_more is None:
                # If has_more is not available, check if we got a full page
                # If we got fewer results than the limit, we're on the last page
                has_more = len(files_response.data) >= limit
            
            if has_more and files_response.data:
                # Get the last file ID to use as 'after' cursor for next page
                after = files_response.data[-1].id
            else:
                # No more pages
                break
        
        LOGGER.info("Retrieved %d files from vector store %s", len(files), vector_store_id)
        return sorted(files, key=lambda x: x["filename"])
    except Exception as e:
        LOGGER.exception("Error listing files in vector store %s: %s", vector_store_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {str(e)}"
        )


def _find_existing_file_id(client: "OpenAI", vector_store_id: str, filename: str) -> Optional[str]:
    files = client.vector_stores.files.list(vector_store_id=vector_store_id)
    for file_obj in files.data:
        try:
            file_details = client.files.retrieve(file_obj.id)
        except Exception:  # pragma: no cover - network failure
            LOGGER.exception("Unable to retrieve file details for %s", file_obj.id)
            continue
        if file_details.filename == filename:
            return file_obj.id
    return None


def _delete_file(client: "OpenAI", vector_store_id: str, file_id: str) -> bool:
    """Remove a file from the vector store and delete it from the file store."""
    success = True
    try:
        client.vector_stores.files.delete(vector_store_id=vector_store_id, file_id=file_id)
        LOGGER.info("Removed file %s from vector store %s", file_id, vector_store_id)
    except Exception as exc:  # pragma: no cover - deletion may fail
        LOGGER.warning("Failed to delete file %s from vector store: %s", file_id, exc)
        success = False

    try:
        client.files.delete(file_id=file_id)
        LOGGER.info("Deleted file %s from OpenAI file store", file_id)
    except Exception as exc:  # pragma: no cover - deletion may fail
        LOGGER.warning("Failed to delete file %s from file store: %s", file_id, exc)
        success = False

    return success


def delete_vector_store_files(
    vector_store_id: str, file_ids: list[str], client: Optional["OpenAI"] = None
) -> dict:
    """Delete one or more files from a vector store and the OpenAI file store."""
    if client is None:
        client = _assert_openai_client()

    if not file_ids:
        return {"deleted": [], "failed": []}

    deleted: list[str] = []
    failed: list[str] = []

    for file_id in file_ids:
        if _delete_file(client, vector_store_id, file_id):
            deleted.append(file_id)
        else:
            failed.append(file_id)

    return {"deleted": deleted, "failed": failed}


def convert_excel_to_txt(excel_path: Path) -> tuple[Path, str]:
    """
    Convert Excel file to text format, preserving all data.
    Returns (converted_file_path, new_filename)
    """
    try:
        import pandas as pd
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pandas library is required for Excel file conversion. Please install it: pip install pandas openpyxl",
        )

    try:
        excel_file = pd.ExcelFile(excel_path, engine='openpyxl')
        output_lines = []
        output_lines.append(f"This file was converted from an Excel workbook: {excel_path.name}")
        output_lines.append(f"Original file path: {excel_path}")
        output_lines.append(f"Total number of sheets: {len(excel_file.sheet_names)}")
        output_lines.append("It contains the following sheets with tabular data:\n")

        total_rows = 0
        total_columns = 0

        for sheet in excel_file.sheet_names:
            try:
                df = pd.read_excel(excel_file, sheet_name=sheet, engine='openpyxl')
                num_rows, num_cols = df.shape
                total_rows += num_rows
                total_columns = max(total_columns, num_cols)

                output_lines.append(f"\n{'='*80}")
                output_lines.append(f"--- Sheet: {sheet} ---")
                output_lines.append(f"Dimensions: {num_rows} rows × {num_cols} columns")
                output_lines.append(f"Column names: {', '.join(df.columns.astype(str).tolist())}")
                output_lines.append(f"{'='*80}\n")

                # Convert to string representation, preserving all data
                pd.set_option('display.max_columns', None)
                pd.set_option('display.max_colwidth', None)
                pd.set_option('display.max_rows', None)

                output_lines.append(df.to_string(index=False, max_rows=None))
                output_lines.append("\n")

                # Reset pandas display options
                pd.reset_option('display.max_columns')
                pd.reset_option('display.max_colwidth')
                pd.reset_option('display.max_rows')

            except Exception as sheet_error:
                output_lines.append(f"\n--- Sheet: {sheet} ---")
                output_lines.append(f"ERROR: Could not process sheet '{sheet}': {str(sheet_error)}\n")
                LOGGER.warning("Error processing sheet '%s' in %s: %s", sheet, excel_path, sheet_error)

        output_lines.append(f"\n{'='*80}")
        output_lines.append(f"Conversion Summary:")
        output_lines.append(f"Total rows across all sheets: {total_rows}")
        output_lines.append(f"Maximum columns in any sheet: {total_columns}")
        output_lines.append(f"{'='*80}\n")

        # Create output file
        output_path = excel_path.with_suffix('.txt')
        output_path.write_text('\n'.join(output_lines), encoding='utf-8')

        # Generate new filename based on original Excel filename
        # Use the original Excel filename stem, not the temp file name
        original_stem = excel_path.stem
        # If it's a temp file, try to preserve original name from path if available
        # Otherwise use the stem
        new_filename = original_stem + '.txt'

        original_size = excel_path.stat().st_size
        converted_size = output_path.stat().st_size
        LOGGER.info(
            "Converted %s: %s bytes -> %s bytes",
            excel_path.name,
            f"{original_size:,}",
            f"{converted_size:,}",
        )

        return output_path, new_filename

    except Exception as e:
        LOGGER.exception("Error converting Excel file %s to text", excel_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to convert Excel file: {str(e)}",
        )


async def ingest_file(file: UploadFile, vector_store_id: Optional[str] = None) -> dict:
    """Upload a file to the OpenAI vector store, replacing previous versions.
    Automatically converts .xlsx files to .txt before upload.
    
    Args:
        file: The file to upload
        vector_store_id: Optional vector store ID. If not provided, uses default from settings.
    """

    validate_upload(file)
    # FastAPI UploadFile uses async read()
    content = await file.read()
    ensure_file_size(content)

    extension = Path(file.filename).suffix.lower()
    original_filename = file.filename
    upload_filename = file.filename
    temp_paths_to_cleanup = []

    # Convert .xlsx to .txt if needed
    if extension in CONVERTIBLE_EXTENSIONS:
        LOGGER.info("Converting %s to text format before upload", file.filename)
        # Preserve original filename for conversion
        original_stem = Path(original_filename).stem
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension, prefix=f"{original_stem}_") as temp_excel:
            temp_excel.write(content)
            excel_path = Path(temp_excel.name)
            temp_paths_to_cleanup.append(excel_path)

        try:
            converted_path, _ = convert_excel_to_txt(excel_path)
            temp_paths_to_cleanup.append(converted_path)
            # Generate proper filename from original
            upload_filename = original_stem + '.txt'
            # Read the converted content
            content = converted_path.read_bytes()
            LOGGER.info("Successfully converted %s to %s", original_filename, upload_filename)
        except Exception as e:
            # Clean up on error
            for path in temp_paths_to_cleanup:
                path.unlink(missing_ok=True)
            raise

    client = _assert_openai_client()
    vector_store_id = _ensure_vector_store(client, vector_store_id)

    # Check for existing file by the upload filename (converted name if applicable)
    existing_file_id = _find_existing_file_id(client, vector_store_id, upload_filename)
    if existing_file_id:
        # File with same name already exists - prevent duplicate upload
        LOGGER.info(
            "File '%s' already exists in vector store %s (file_id: %s). Skipping upload to prevent duplicates.",
            upload_filename,
            vector_store_id,
            existing_file_id,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"File '{upload_filename}' already exists in the vector store. Please delete the existing file first if you want to replace it.",
        )

    # Upload file to OpenAI Files API first, then add to vector store
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(upload_filename).suffix) as temp:
        temp.write(content)
        upload_path = Path(temp.name)
        temp_paths_to_cleanup.append(upload_path)

    try:
        # Step 1: Upload file to OpenAI Files API
        # OpenAI API requires file as (filename, file_object, content_type) tuple
        import mimetypes
        content_type, _ = mimetypes.guess_type(upload_filename)
        if not content_type:
            content_type = "application/octet-stream"
        
        with upload_path.open("rb") as handle:
            file_response = client.files.create(
                file=(upload_filename, handle, content_type),
                purpose="assistants"
            )
            file_id = file_response.id
            LOGGER.info("Uploaded file %s to OpenAI Files API with ID: %s", upload_filename, file_id)

        # Step 2: Add file to vector store
        # Use create_and_poll with timeout to prevent hanging
        import asyncio
        try:
            # Run the blocking create_and_poll in an executor with timeout
            loop = asyncio.get_event_loop()
            vs_file = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: client.vector_stores.files.create_and_poll(
                        vector_store_id=vector_store_id,
                        file_id=file_id
                    )
                ),
                timeout=300.0  # 5 minute timeout
            )
            LOGGER.info("Added file %s to vector store %s", upload_filename, vector_store_id)
        except asyncio.TimeoutError:
            LOGGER.error("Timeout adding file %s to vector store after 5 minutes", upload_filename)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="File upload timed out. The file may still be processing. Please check the vector store status."
            )
        
        # Get updated vector store info
        vs_info = client.vector_stores.retrieve(vector_store_id)
        file_count = vs_info.file_counts.total if hasattr(vs_info, "file_counts") else 1
        
    finally:
        # Clean up all temporary files
        for path in temp_paths_to_cleanup:
            path.unlink(missing_ok=True)

    return {
        "vector_store_id": vector_store_id,
        "file_id": file_id,
        "file_count": file_count,
        "status": getattr(vs_file, "status", "completed"),
        "original_filename": original_filename,
        "uploaded_filename": upload_filename,
        "converted": extension in CONVERTIBLE_EXTENSIONS,
    }
