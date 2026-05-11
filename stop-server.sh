#!/usr/bin/env bash
# Stop backend + word-plugin dev servers.
# Usage: ./stop-server.sh

echo "Stopping backend (port 8003)..."
pkill -f "uvicorn backend.main" 2>/dev/null && echo "  Stopped." || echo "  Not running."

echo "Stopping word-plugin (port 3000)..."
pkill -f "vite.*--port 3000" 2>/dev/null && echo "  Stopped." || echo "  Not running."
