#!/bin/sh
set -eu
DEMO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
REPO_DIR=$(CDPATH= cd -- "$DEMO_DIR/../.." && pwd -P)
exec "$REPO_DIR/.venv/bin/python" "$DEMO_DIR/../banca-demo-support/demo.py" --authorize-writes "$@"
