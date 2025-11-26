#!/bin/bash
# Startup script for Cloud Run - reads PORT environment variable
PORT=${PORT:-8080}
echo "Launching uvicorn on port ${PORT}"
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT}"
