#!/usr/bin/env sh

set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
RUN_SCRIPT="$PROJECT_ROOT/run.sh"
BIN_DIRECTORY="$HOME/.local/bin"
LAUNCHER="$BIN_DIRECTORY/nova-team"

if [ ! -f "$RUN_SCRIPT" ]; then
    printf '%s\n' "run.sh was not found in the project root." >&2
    exit 1
fi

mkdir -p "$BIN_DIRECTORY"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env sh
exec "$RUN_SCRIPT" "\$@"
EOF
chmod +x "$LAUNCHER"

printf '%s\n' "Nova Team launcher installed."
if ! printf ':%s:' "$PATH" | grep -Fq ":$BIN_DIRECTORY:"; then
    printf '%s\n' "Add this line to ~/.zshrc to make nova-team available in new shells:"
    printf '%s\n' 'export PATH="$HOME/.local/bin:$PATH"'
fi
