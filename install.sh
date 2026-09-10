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
"$UV" tool install --force "$ROOT"

USER_BIN=$HOME/.local/bin
case ":${PATH:-}:" in
  *":$USER_BIN:"*) : ;;
  *) printf '%s\n' "Add $USER_BIN to PATH, or run: uv tool update-shell" ;;
esac

printf '%s\n' "Installed without sudo. Start with: deepclean"
