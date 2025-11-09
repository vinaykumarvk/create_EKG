# Create EKG Admin Console

This project exposes a hardened FastAPI admin experience for managing an OpenAI vector store. Administrators can upload local documents or ingest data directly from a Google Drive folder while the system takes care of re-embedding files whenever newer copies are provided.

## Features

- **Secure authentication** – PBKDF2 hashed admin password, CSRF protection, secure session cookies, and defensive HTTP headers.
- **Document validation** – Rejects empty uploads, enforces a 100&nbsp;MB size limit, and accepts a curated list of document types (PDF, TXT, Markdown, DOCX, CSV, JSON).
- **Vector store automation** – Automatically creates a vector store when needed, removes stale embeddings, and ingests updated content through the OpenAI Files API.
- **Google Drive integration** – Optional service-account integration for browsing and importing files from Drive folders directly within the admin dashboard.
- **Responsive UI** – A clean glassmorphism-inspired dashboard built with vanilla HTML/CSS/JS to keep dependencies minimal.

## Getting started

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**

   Create a `.env` file based on the template below:

   ```env
   SESSION_SECRET=change-me-32-characters-minimum
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD_HASH=pbkdf2$...
   OPENAI_API_KEY=sk-...
   OPENAI_VECTOR_STORE_ID=vs_...
   GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
   GOOGLE_IMPERSONATED_USER=admin@example.com
   ```

   Generate a password hash with:

   ```bash
   python - <<'PY'
   from api.security import hash_password
   print(hash_password('your-strong-password'))
   PY
   ```

   The Google settings are optional; omit them if Google Drive ingestion is not required.

3. **Run the development server**

   ```bash
   uvicorn api.main:app --reload
   ```

4. **Execute tests**

   ```bash
   pytest
   ```

## Project structure

- `api/settings.py` – Environment-driven configuration using lightweight dataclasses.
- `api/main.py` – FastAPI application, routes, and middleware.
- `api/security.py` – Password hashing and CSRF helpers.
- `api/session.py` – Session helpers and flash messaging utilities.
- `api/vector_store.py` – OpenAI vector store orchestration.
- `api/google_drive.py` – Optional Google Drive folder browsing and downloads.
- `api/templates/` – Jinja2 templates for the login and admin dashboard.
- `api/static/` – CSS and JavaScript assets for the admin interface.

## Suggested enhancements

- Add multi-factor authentication (MFA) support for administrators via TOTP.
- Persist ingestion history with timestamps and file metadata for audit trails.
- Integrate notifications (email/Slack) whenever the vector store is updated.
- Provide health monitoring endpoints and structured logging.
- Offer pre-processing hooks for chunking and text cleanup prior to embedding.
