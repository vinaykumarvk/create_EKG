"""FastAPI application exposing the Create EKG admin console."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette import status
from starlette.middleware.sessions import SessionMiddleware

from .google_drive import (
    GoogleDriveClient,
    extract_folder_id,
    validate_drive_file_size,
)
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
from .vector_store import MAX_FILE_BYTES, ingest_file

LOGGER = logging.getLogger(__name__)


def get_drive_client() -> GoogleDriveClient:
    return GoogleDriveClient(
        credentials_file=str(settings.google_service_account_file)
        if settings.google_service_account_file
        else None,
        impersonated_user=settings.google_impersonated_user,
    )


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=True,
        same_site="lax",
    )

    static_path = Path(__file__).parent / "static"
    templates_path = Path(__file__).parent / "templates"
    app.mount("/static", StaticFiles(directory=static_path), name="static")
    templates = Jinja2Templates(directory=str(templates_path))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'")
        return response

    def render(template: str, request: Request, **context):
        context.setdefault("settings", settings)
        context.setdefault("csrf_token", get_csrf_token(request))
        context.setdefault("flash", consume_flash(request))
        context.setdefault("drive_enabled", get_drive_client().enabled)
        return templates.TemplateResponse(template, {"request": request, **context})

    def require_login(request: Request) -> None:
        if not is_authenticated(request):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

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

        require_admin_password(password, settings.admin_password_hash)
        login_admin(request)
        flash_message(request, "Welcome back!", "success")
        return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/logout")
    async def do_logout(request: Request, csrf_token: str = Form(...)):
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)
        logout_admin(request)
        flash_message(request, "You have been signed out.")
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_dashboard(request: Request):
        require_login(request)
        return render("admin_dashboard.html", request, max_file_bytes=MAX_FILE_BYTES)

    @app.post("/upload")
    async def upload_file(
        request: Request,
        file: UploadFile = File(...),
        csrf_token: str = Form(...),
    ):
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        result = ingest_file(file)
        flash_message(request, "File ingested successfully!", "success")
        return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)

    @app.post("/google-drive/list")
    async def list_google_drive(
        request: Request,
        folder_link: str = Form(...),
        csrf_token: str = Form(...),
        drive_client: GoogleDriveClient = Depends(get_drive_client),
    ):
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        folder_id = extract_folder_id(folder_link)
        if not folder_id:
            raise HTTPException(status_code=400, detail="Invalid Google Drive folder link")

        files = drive_client.list_folder(folder_id)
        for entry in files:
            validate_drive_file_size(entry.get("size"), MAX_FILE_BYTES)
        return {"files": files}

    @app.post("/google-drive/ingest")
    async def ingest_google_drive_file(
        request: Request,
        file_id: str = Form(...),
        file_name: str = Form(...),
        csrf_token: str = Form(...),
        drive_client: GoogleDriveClient = Depends(get_drive_client),
    ):
        require_login(request)
        session_token = get_csrf_token(request)
        validate_csrf_token(session_token, csrf_token)

        if not drive_client.enabled:
            raise HTTPException(status_code=503, detail="Google Drive integration not configured")

        content = drive_client.download_file(file_id)
        validate_drive_file_size(str(len(content)), MAX_FILE_BYTES)

        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            with tmp_path.open('rb') as handle:
                upload = UploadFile(filename=file_name, file=handle)
                ingest_file(upload)
        finally:
            tmp_path.unlink(missing_ok=True)

        flash_message(request, f"Imported {file_name} from Google Drive", "success")
        return RedirectResponse("/admin", status_code=status.HTTP_303_SEE_OTHER)

    return app


app = create_app()
