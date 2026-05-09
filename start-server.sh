#!/usr/bin/env bash
# Start backend + frontend for local development.
# Usage: ./dev.sh

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

# Backend
echo "Starting backend on :8000 ..."
SPRIH_AUTH_DEV_MODE=true uv run uvicorn backend.main:app --reload --port 8000 &
BACKEND_PID=$!

# Frontend (Word add-in served by Vite over HTTPS)
echo "Starting word-plugin on :3000 ..."
cd "$ROOT/word-plugin" && npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend:  http://localhost:8000  (API docs: http://localhost:8000/docs)"
echo "Frontend: https://localhost:3000  (Word add-in — HTTPS)"
echo "Press Ctrl+C to stop both."
echo ""

wait
