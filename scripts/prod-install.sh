#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(uname -s)" = "Darwin" ] || fail "prod-install supports macOS only."
[ "$(id -u)" -ne 0 ] || fail "Do not run prod-install with sudo/root."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." 2>/dev/null && pwd -P) || fail "Could not resolve project root."
cd "$ROOT"

CARGO=$(command -v cargo 2>/dev/null || true)
[ -n "$CARGO" ] || fail "cargo is required for compiling MacMaid from source. Install Rust via https://rustup.rs."

APP_NAME=${APP_NAME:-MacMaid}
BIN_NAME=${BIN_NAME:-macmaid}
INSTALL_BIN_DIR=${INSTALL_BIN_DIR:-$HOME/.local/bin}
INSTALL_APP_DIR=${INSTALL_APP_DIR:-$HOME/Applications}

case "$ROOT" in
  "$HOME"|"$HOME"/*) : ;;
  *) info "Warning: project is outside HOME. If macOS blocks the build, move it under your home directory." ;;
esac

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true
fi

info "Building native MacMaid desktop application and CLI with scripts/build-macos-app.sh..."
./scripts/build-macos-app.sh

BUILD_APP="$ROOT/build/macos-app/MacMaid.app"
BUILD_CLI="$ROOT/build/macos-app/cli/$BIN_NAME"

[ -d "$BUILD_APP" ] || fail "Native application bundle not found at $BUILD_APP"
[ -x "$BUILD_CLI" ] || fail "CLI binary not found at $BUILD_CLI"

mkdir -p "$INSTALL_BIN_DIR" "$INSTALL_APP_DIR"

info "Installing $BIN_NAME CLI to $INSTALL_BIN_DIR/$BIN_NAME..."
cp -f "$BUILD_CLI" "$INSTALL_BIN_DIR/$BIN_NAME"
chmod 755 "$INSTALL_BIN_DIR/$BIN_NAME"

APP_DEST="$INSTALL_APP_DIR/$APP_NAME.app"
info "Installing native macOS application to $APP_DEST..."
rm -rf "$APP_DEST"
cp -R "$BUILD_APP" "$APP_DEST"

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$INSTALL_BIN_DIR/$BIN_NAME" "$APP_DEST" >/dev/null 2>&1 || true
fi

"$INSTALL_BIN_DIR/$BIN_NAME" --version >/dev/null || fail "Installed binary smoke test failed."

ACTIVE_SHELL=${SHELL##*/}
case "$ACTIVE_SHELL" in
  zsh|bash|fish)
    if "$INSTALL_BIN_DIR/$BIN_NAME" completion "$ACTIVE_SHELL" --install >/dev/null 2>&1; then
      info "Shell completion installed for $ACTIVE_SHELL. Open a new terminal for Tab completion."
    else
      info "Shell completion could not be installed automatically. You can print it with: $BIN_NAME completion $ACTIVE_SHELL --print"
    fi
    ;;
  *) info "Shell completion was not changed for unsupported shell: ${ACTIVE_SHELL:-unknown}" ;;
esac

case ":${PATH:-}:" in
  *":$INSTALL_BIN_DIR:"*) : ;;
  *) info "Add $INSTALL_BIN_DIR to PATH to run '$BIN_NAME' from any terminal." ;;
esac

info "Production install complete:"
info "  CLI: $INSTALL_BIN_DIR/$BIN_NAME"
info "  App: $APP_DEST"
info "Launch with: open '$APP_DEST'"
