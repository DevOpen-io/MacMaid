#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || fail "DeepClean supports macOS only."
[ "$(id -u)" -ne 0 ] || fail "Do not install DeepClean with sudo/root. Run ./install.sh as your normal user."

UV=$(command -v uv 2>/dev/null || true)
[ -n "$UV" ] || fail "uv is required. Install it from https://docs.astral.sh/uv/ then rerun ./install.sh"

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR" 2>/dev/null && pwd -P) || fail "Could not resolve project directory."

printf '%s\n' "Installing DeepClean into your user-owned uv tool directory..."

# Ensure the uv tool bin directory exists and is writable
TOOL_BIN=$("$UV" tool dir --bin)
if [ ! -d "$TOOL_BIN" ]; then
  printf '%s\n' "Creating tool directory: $TOOL_BIN"
  mkdir -p "$TOOL_BIN" || fail "Could not create tool directory: $TOOL_BIN"
else
  # Directory exists - check ownership and permissions
  DIR_OWNER=$(stat -f "%u" "$TOOL_BIN" 2>/dev/null || echo "unknown")
  CURRENT_USER=$(id -u)
  if [ "$DIR_OWNER" != "$CURRENT_USER" ]; then
    fail "Tool directory $TOOL_BIN is owned by user $DIR_OWNER, not you ($CURRENT_USER). Fix with: sudo chown $CURRENT_USER $TOOL_BIN"
  fi
fi

# Check if the directory is writable
if [ ! -w "$TOOL_BIN" ]; then
  DIR_PERMS=$(stat -f "%A" "$TOOL_BIN" 2>/dev/null || echo "unknown")
  fail "Tool directory is not writable: $TOOL_BIN (permissions: $DIR_PERMS). Fix with: chmod u+w $TOOL_BIN"
fi

"$UV" tool install --force "$ROOT"

ACTIVE_SHELL=${SHELL##*/}
case "$ACTIVE_SHELL" in
  zsh|bash|fish)
    if "$TOOL_BIN/deepclean" completion "$ACTIVE_SHELL" --install; then
      printf '%s\n' "Shell completion installed automatically for $ACTIVE_SHELL."
    else
      printf '%s\n' "DeepClean was installed, but $ACTIVE_SHELL completion could not be configured." >&2
    fi
    ;;
  *) printf '%s\n' "Shell completion was not changed for unsupported shell: ${ACTIVE_SHELL:-unknown}" ;;
esac

USER_BIN=$HOME/.local/bin
case ":${PATH:-}:" in
  *":$USER_BIN:"*) : ;;
  *) printf '%s\n' "Add $USER_BIN to PATH, or run: uv tool update-shell" ;;
esac

printf '%s\n' "Installed without sudo. Start with: deepclean"
