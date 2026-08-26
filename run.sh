#!/usr/bin/env sh

set -u

if [ "${1-}" = "--help" ]; then
    printf '%s\n' "Autonomous Engineering Team" "" "Windows:" "  .\\run.ps1" "" "macOS:" "  ./run.sh" "" "The script expects the project to be already configured."
    exit 0
fi

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
PYTHON="$PROJECT_ROOT/.venv/bin/python"

if [ ! -f "$PYTHON" ]; then
    printf '%s\n' "Project is not prepared." "Please complete the project setup first." >&2
    exit 1
fi

ollama_ready() {
    "$PYTHON" -c 'from urllib.request import urlopen; urlopen("http://localhost:11434/api/tags", timeout=2).close()' >/dev/null 2>&1
}

if ! ollama_ready; then
    if ! command -v ollama >/dev/null 2>&1; then
        printf '%s\n' "Ollama is not available. Start Ollama and try again." >&2
        exit 1
    fi

    ollama serve >/dev/null 2>&1 &
    sleep 3
    if ! ollama_ready; then
        printf '%s\n' "Ollama did not respond at http://localhost:11434." >&2
        exit 1
    fi
fi

printf '%s\n' "Autonomous Engineering Team" "----------------------------" ""
requirement=""
while [ -z "$(printf '%s' "$requirement" | tr -d '[:space:]')" ]; do
    printf '%s' "Enter requirement: "
    IFS= read -r requirement || exit 1
    if [ -z "$(printf '%s' "$requirement" | tr -d '[:space:]')" ]; then
        printf '%s\n' "A requirement is required."
    fi
done

printf '%s\n' "" "Starting engineering team..."
cd "$PROJECT_ROOT" || exit 1
exec "$PYTHON" -m engineering_team.cli run "$requirement"
