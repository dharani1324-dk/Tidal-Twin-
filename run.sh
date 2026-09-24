#!/usr/bin/env bash
# TidalTwin - local development launcher (macOS / Linux)
# ======================================================
# Starts the backend API and the frontend dev server together.
# For the containerised, one-command deployment use:
#     docker compose up --build
#
# Usage:
#     ./run.sh
#
# Prerequisites: Python 3.12+, Node 20+, a reachable PostgreSQL+PostGIS,
# and a configured backend/.env (see backend/.env.example).

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

command -v node >/dev/null 2>&1 || { echo "Node.js is required (https://nodejs.org)."; exit 1; }
command -v npm  >/dev/null 2>&1 || { echo "npm is required (ships with Node.js)."; exit 1; }

if [ -x "$BACKEND/.venv/bin/python" ]; then
  PYTHON="$BACKEND/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "Python 3.12+ is required (https://python.org)."; exit 1
fi

echo "[tidaltwin] Starting backend on http://127.0.0.1:8000 ..."
( cd "$BACKEND" && "$PYTHON" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 ) &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "[tidaltwin] Installing frontend dependencies (first run) ..."
  ( cd "$FRONTEND" && npm install )
fi

echo "[tidaltwin] Starting frontend on http://127.0.0.1:5173 ..."
echo "[tidaltwin] Press Ctrl+C to stop both."
cd "$FRONTEND" && npm run dev
