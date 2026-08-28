#!/usr/bin/env sh
# Stops the backend (uvicorn) and frontend (vite) dev servers started by start_systems.sh.

set -u

stopped=0

for pattern in "uvicorn sample_app.app.main:app" "vite"; do
    pids=$(pgrep -f "$pattern" 2>/dev/null)
    if [ -n "$pids" ]; then
        # shellcheck disable=SC2086
        kill $pids 2>/dev/null
        stopped=1
    fi
done

if [ "$stopped" = 1 ]; then
    printf '%s\n' "Stopped backend and/or frontend processes."
else
    printf '%s\n' "No running backend/frontend processes found."
fi
