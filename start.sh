#!/usr/bin/env bash
# DataLab start script — builds the frontend (first run) and serves the whole
# app (API + UI) with a single uvicorn process on port 3000.
set -e
cd "$(dirname "$0")"

if [ ! -d frontend/dist ]; then
  echo "[start] frontend/dist not found — building the frontend..."
  (cd frontend && npm install && npm run build)
fi

echo "[start] starting DataLab on http://0.0.0.0:3000"
cd backend
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 3000
