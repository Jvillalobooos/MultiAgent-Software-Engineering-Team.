#!/usr/bin/env sh
# Starts the FastAPI backend and the Vite frontend dev server together.
# Ctrl+C stops both.

set -u

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    printf '%s\n' "Project is not prepared: $PYTHON not found." "Set up the .venv first." >&2
    exit 1
fi

if [ ! -d "$PROJECT_ROOT/frontend/node_modules" ]; then
    printf '%s\n' "frontend/node_modules not found." "Run 'npm install' in frontend/ first." >&2
    exit 1
fi

cleanup() {
    trap - INT TERM EXIT
    [ -n "${BACKEND_PID-}" ] && kill "$BACKEND_PID" 2>/dev/null
    [ -n "${FRONTEND_PID-}" ] && kill "$FRONTEND_PID" 2>/dev/null
    wait 2>/dev/null
}
trap cleanup INT TERM EXIT

printf '%s\n' "Starting backend (FastAPI on http://127.0.0.1:8000)..."
(cd "$PROJECT_ROOT" && exec "$PYTHON" -m uvicorn sample_app.app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

printf '%s\n' "Starting frontend (Vite on http://localhost:5173)..."
(cd "$PROJECT_ROOT/frontend" && exec npm run dev) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
