"""FastAPI application for Create EKG admin console."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status
from starlette.middleware.sessions import SessionMiddleware

from .security import require_admin_password, validate_csrf_token
from .session import (
    consume_flash,
    flash_message,
    get_csrf_token,
    is_authenticated,
    login_admin,
    logout_admin,
)
from .settings import settings
from .vector_store import (
    MAX_FILE_BYTES,
    ingest_file,
    list_vector_stores,
    create_vector_store,
    list_vector_store_files,
    delete_vector_store_files,
)

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    # Session middleware - allow HTTP for local development
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=False,
        same_site="lax",
    )

    # Static files and templates
    static_path = Path(__file__).parent / "static"
    templates_path = Path(__file__).parent / "templates"
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    templates = Jinja2Templates(directory=str(templates_path))

    # Security headers
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        return response

    def render(template: str, request: Request, **context):
        context.setdefault("settings", settings)
        context.setdefault("csrf_token", get_csrf_token(request))
        context.setdefault("flash", consume_flash(request))
        return templates.TemplateResponse(template, {"request": request, **context})

    def require_login(request: Request) -> None:
        if not is_authenticated(request):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Routes
    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        if is_authenticated(request):
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        return render("login.html", request)

    @app.get("/login", response_class=HTMLResponse)
    async def login(request: Request):
        if is_authenticated(request):
            return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)
        return render("login.html", request)

    @app.post("/login")
    async def do_login(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        csrf_token: str = Form(...),
    ):
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        if username != settings.admin_username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        try:
            require_admin_password(password, settings.admin_password_hash)
            login_admin(request)
            flash_message(request, "Welcome back!", "success")
            return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)
        except HTTPException:
            raise

    @app.post("/logout")
    async def do_logout(request: Request, csrf_token: str = Form(...)):
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)
        logout_admin(request)
        flash_message(request, "You have been signed out.")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/favicon.ico")
    async def favicon():
        from fastapi.responses import Response
        return Response(content=b"", media_type="image/x-icon")

    @app.get("/forgot-password", response_class=HTMLResponse)
    async def forgot_password(request: Request):
        """Placeholder for forgot password - not implemented yet."""
        flash_message(request, "Password reset functionality is not yet implemented.", "info")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_dashboard(request: Request):
        require_login(request)
        
        # Get vector stores
        stores = []
        default_store = None
        try:
            stores = list_vector_stores()
            # Find default store
            if settings.openai_vector_store_id:
                for store in stores:
                    if store["id"] == settings.openai_vector_store_id:
                        default_store = store
                        break
            if not default_store and stores:
                default_store = stores[0]
        except Exception as e:
            LOGGER.exception("Error loading vector stores: %s", e)
            flash_message(request, f"Warning: Could not load vector stores: {str(e)[:100]}", "error")

        return render(
            "admin_dashboard.html",
            request,
            max_file_bytes=MAX_FILE_BYTES,
            vector_stores=stores,
            default_vector_store=default_store,
        )

    @app.post("/upload")
    async def upload_file(
        request: Request,
        files: list[UploadFile] = File(...),
        vector_store_id: Optional[str] = Form(None),
        csrf_token: str = Form(...),
    ):
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        # Convert empty string to None
        if vector_store_id == "":
            vector_store_id = None

        if not files:
            flash_message(request, "No files selected for upload.", "error")
            return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)

        all_files = files

        results = []
        errors = []

        for upload_file in all_files:
            try:
                LOGGER.info("Uploading file: %s to vector store: %s", upload_file.filename, vector_store_id or "default")
                result = await ingest_file(upload_file, vector_store_id=vector_store_id)
                results.append(result)
                
                if result.get("converted"):
                    flash_message(
                        request,
                        f"File '{result.get('original_filename')}' converted to '{result.get('uploaded_filename')}' and uploaded successfully!",
                        "success",
                    )
                else:
                    flash_message(request, f"File '{upload_file.filename}' uploaded successfully!", "success")
            except HTTPException as e:
                # Extract the detail message from HTTPException
                error_msg = getattr(e, 'detail', None) or str(e)
                # Include filename in the message if not already present
                if upload_file.filename and upload_file.filename not in error_msg:
                    error_msg = f"File '{upload_file.filename}': {error_msg}"
                LOGGER.warning("Upload rejected for file %s: %s (status: %s)", upload_file.filename, error_msg, getattr(e, 'status_code', 'unknown'))
                errors.append(error_msg)
                flash_message(request, error_msg, "error")
                LOGGER.info("Flash message set: %s", error_msg)
            except Exception as e:
                LOGGER.exception("Error uploading file %s: %s", upload_file.filename, e)
                error_msg = f"Error uploading '{upload_file.filename}': {str(e)[:200]}"
                errors.append(error_msg)
                flash_message(request, error_msg, "error")

        # If all succeeded, show summary
        if results and not errors:
            if len(results) > 1:
                flash_message(request, f"Successfully uploaded {len(results)} files!", "success")
        
        return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/api/vector-stores")
    async def get_vector_stores_api(request: Request):
        require_login(request)
        try:
            stores = list_vector_stores()
            return JSONResponse(content=stores)
        except Exception as e:
            LOGGER.exception("Error listing vector stores: %s", e)
            return JSONResponse(
                content={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @app.post("/api/vector-stores/create")
    async def create_vector_store_api(
        request: Request,
        name: str = Form(...),
        csrf_token: str = Form(...),
    ):
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        try:
            store = create_vector_store(name)
            return JSONResponse(content=store)
        except Exception as e:
            LOGGER.exception("Error creating vector store: %s", e)
            return JSONResponse(
                content={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @app.get("/api/vector-stores/{vector_store_id}/files")
    async def get_vector_store_files_api(request: Request, vector_store_id: str):
        """API endpoint to get list of files in a vector store."""
        require_login(request)
        try:
            files = list_vector_store_files(vector_store_id)
            return JSONResponse(content={"files": files})
        except Exception as e:
            LOGGER.exception("Error listing files: %s", e)
            return JSONResponse(
                content={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @app.post("/api/vector-stores/{vector_store_id}/files/delete")
    async def delete_vector_store_files_api(
        request: Request,
        vector_store_id: str,
        file_ids: List[str] = Form(...),
        csrf_token: str = Form(...),
    ):
        """API endpoint to delete files from a vector store."""
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        if not file_ids:
            return JSONResponse(
                content={"error": "No files selected for deletion."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = delete_vector_store_files(vector_store_id, file_ids)
            status_code = (
                status.HTTP_200_OK
                if not result["failed"]
                else status.HTTP_207_MULTI_STATUS
            )
            return JSONResponse(content=result, status_code=status_code)
        except HTTPException:
            raise
        except Exception as e:
            LOGGER.exception("Error deleting files: %s", e)
            return JSONResponse(
                content={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    return app


app = create_app()
