#!/usr/bin/env bash

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
cd "$ROOT"

PYTHON="$REPO/.venv/Scripts/python.exe"

if [ ! -f "$PYTHON" ]; then
    echo ".venv not found. Run: uv sync (from repo root)"
    exit 1
fi

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

echo "Starting backend on :8000 ..."

SPRIH_AUTH_DEV_MODE=True "$PYTHON" -m uvicorn backend.main:app \
  --reload \
  --reload-dir backend \
  --port 8000 &
BACKEND_PID=$!

echo "Starting frontend on :3000 ..."

cd "$ROOT/../wordgpt-main"
yarn dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://127.0.0.1:8000  (docs: http://127.0.0.1:8000/docs)"
echo "Frontend: http://localhost:3000"
echo "Press Ctrl+C to stop both."
echo ""

wait