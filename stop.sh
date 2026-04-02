#!/usr/bin/env bash
# Stop backend + frontend dev servers.
# Usage: ./stop.sh

echo "Stopping backend (port 8000)..."
kill $(lsof -ti:8000) 2>/dev/null && echo "  Stopped." || echo "  Not running."

echo "Stopping frontend (port 3000)..."
kill $(lsof -ti:3000) 2>/dev/null && echo "  Stopped." || echo "  Not running."
