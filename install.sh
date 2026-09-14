#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(uname -s)" = "Darwin" ] || fail "DeepClean supports macOS only."
[ "$(id -u)" -ne 0 ] || fail "Do not install DeepClean with sudo/root. Run sh install.sh as your normal user."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR" 2>/dev/null && pwd -P) || fail "Could not resolve project directory."

# Archives downloaded from browsers/AirDrop can carry quarantine metadata.  It is
# safe to clear it from this source checkout before building the user-local tool;
# ignore failures because managed/company Macs may disallow changing xattrs.
if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true
fi

# DeepClean is installed user-locally through uv.  To make the project usable on
# a fresh Mac, bootstrap uv into the current user's home directory when it is not
# already present.  This keeps installation rootless and avoids /usr/local writes.
UV=$(command -v uv 2>/dev/null || true)
if [ -z "$UV" ]; then
  info "uv was not found; installing uv for the current user..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || fail "uv installation failed. Install uv manually, then rerun: sh install.sh"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh || fail "uv installation failed. Install uv manually, then rerun: sh install.sh"
  else
    fail "uv is required and neither curl nor wget is available. Install uv, then rerun: sh install.sh"
  fi
  # The installer cannot modify this already-running shell, so discover uv in
  # the standard user-local locations immediately.
  for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    if [ -x "$candidate" ]; then UV=$candidate; break; fi
  done
  [ -n "$UV" ] || UV=$(command -v uv 2>/dev/null || true)
  [ -n "$UV" ] || fail "uv was installed but is not on PATH. Open a new terminal or add ~/.local/bin to PATH, then rerun: sh install.sh"
fi

info "Installing DeepClean into your user-owned uv tool directory..."

TOOL_BIN=$($UV tool dir --bin 2>/dev/null) || fail "Could not determine uv tool bin directory."
if [ ! -d "$TOOL_BIN" ]; then
  info "Creating tool directory: $TOOL_BIN"
  mkdir -p "$TOOL_BIN" 2>/dev/null || fail "Could not create tool directory: $TOOL_BIN. Check macOS privacy permissions or choose a user-writable HOME."
fi

DIR_OWNER=$(stat -f "%u" "$TOOL_BIN" 2>/dev/null || echo "unknown")
CURRENT_USER=$(id -u)
if [ "$DIR_OWNER" != "unknown" ] && [ "$DIR_OWNER" != "$CURRENT_USER" ]; then
  fail "uv tool directory is not owned by the current user: $TOOL_BIN. Reinstall uv as your normal user or set UV_TOOL_BIN_DIR to a user-owned directory."
fi

if [ ! -w "$TOOL_BIN" ]; then
  DIR_PERMS=$(stat -f "%A" "$TOOL_BIN" 2>/dev/null || echo "unknown")
  fail "uv tool directory is not writable: $TOOL_BIN (permissions: $DIR_PERMS). Use a user-owned uv installation or set UV_TOOL_BIN_DIR to a writable directory."
fi

"$UV" tool install --python 3.11 --force "$ROOT" || fail "DeepClean installation failed. If macOS reported 'Operation not permitted', move this folder under your home directory and run: sh install.sh"

ACTIVE_SHELL=${SHELL##*/}
case "$ACTIVE_SHELL" in
  zsh|bash|fish)
    if "$TOOL_BIN/deepclean" completion "$ACTIVE_SHELL" --install >/dev/null 2>&1; then
      info "Shell completion installed automatically for $ACTIVE_SHELL."
    else
      info "DeepClean was installed; shell completion was skipped because the shell config is not writable."
    fi
    ;;
  *) info "Shell completion was not changed for unsupported shell: ${ACTIVE_SHELL:-unknown}" ;;
esac

case ":${PATH:-}:" in
  *":$TOOL_BIN:"*) : ;;
  *) info "Add $TOOL_BIN to PATH, or run: $UV tool update-shell" ;;
esac

info "Installed without sudo. Start with: $TOOL_BIN/deepclean"
