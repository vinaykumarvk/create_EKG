#!/bin/bash
# Startup script for Cloud Run - reads PORT environment variable
PORT=${PORT:-8000}
exec uvicorn api.main:app --host 0.0.0.0 --port $PORT

