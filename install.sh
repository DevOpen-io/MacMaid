#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(uname -s)" = "Darwin" ] || fail "MacMaid supports macOS only."
[ "$(id -u)" -ne 0 ] || fail "Do not install MacMaid with sudo/root. Run sh install.sh as your normal user."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR" 2>/dev/null && pwd -P) || fail "Could not resolve project directory."

# Clear quarantine flags if present
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true
fi

CARGO=$(command -v cargo 2>/dev/null || true)
if [ -z "$CARGO" ]; then
  for candidate in "$HOME/.cargo/bin/cargo" "/opt/homebrew/bin/cargo"; do
    if [ -x "$candidate" ]; then CARGO=$candidate; break; fi
  done
fi

[ -n "$CARGO" ] || fail "Rust (cargo) is required to build MacMaid. Install Rust via https://rustup.rs and rerun: sh install.sh"

info "Installing MacMaid..."
sh "$ROOT/scripts/prod-install.sh"
