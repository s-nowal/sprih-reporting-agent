#!/usr/bin/env bash
# Stop backend + frontend dev servers.
# Usage: ./stop-server.sh

echo "Stopping backend (port 8000)..."
pkill -f "uvicorn backend.main" 2>/dev/null && echo "  Stopped." || echo "  Not running."

echo "Stopping frontend (port 3000)..."
pkill -f "next dev" 2>/dev/null && echo "  Stopped." || echo "  Not running."
