#!/bin/sh
set -eu

fail() { printf '%s\n' "$*" >&2; exit 1; }
info() { printf '%s\n' "$*"; }

[ "$(uname -s)" = "Darwin" ] || fail "prod-install supports macOS only."
[ "$(id -u)" -ne 0 ] || fail "Do not run prod-install with sudo/root."

SCRIPT_DIR=$(dirname "$0")
ROOT=$(CDPATH= cd "$SCRIPT_DIR/.." 2>/dev/null && pwd -P) || fail "Could not resolve project root."
cd "$ROOT"

UV=${UV:-$(command -v uv 2>/dev/null || true)}
[ -n "$UV" ] || fail "uv is required for production packaging. Run sh install.sh once or install uv manually."

PYTHON_VERSION=${PYTHON_VERSION:-3.11}
APP_NAME=${APP_NAME:-DeepClean}
BIN_NAME=${BIN_NAME:-deepclean}
INSTALL_BIN_DIR=${INSTALL_BIN_DIR:-$HOME/.local/bin}
INSTALL_APP_DIR=${INSTALL_APP_DIR:-$HOME/Applications}
BUILD_DIR=${BUILD_DIR:-$ROOT/build/prod}
ENTRYPOINT=$BUILD_DIR/deepclean_entry.py
DIST_DIR=$BUILD_DIR/dist
WORK_DIR=$BUILD_DIR/work
SPEC_DIR=$BUILD_DIR/spec

case "$ROOT" in
  "$HOME"|"$HOME"/*) : ;;
  *) info "Warning: project is outside HOME. If macOS blocks the build, move it under your home directory." ;;
esac

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true
fi

mkdir -p "$BUILD_DIR" "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR" "$INSTALL_BIN_DIR" "$INSTALL_APP_DIR"
cat > "$ENTRYPOINT" <<'PY'
from deepclean import main

if __name__ == "__main__":
    main()
PY

info "Building standalone DeepClean binary with PyInstaller..."
"$UV" run --python "$PYTHON_VERSION" --with pyinstaller pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name "$BIN_NAME" \
  --distpath "$DIST_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$SPEC_DIR" \
  --paths "$ROOT/src" \
  --add-data "$ROOT/src/deepclean/WebUI:deepclean/WebUI" \
  --collect-all textual \
  "$ENTRYPOINT"

BINARY=$DIST_DIR/$BIN_NAME
[ -x "$BINARY" ] || fail "PyInstaller did not produce $BINARY"

if command -v codesign >/dev/null 2>&1; then
  info "Applying ad-hoc code signature..."
  codesign --force --sign - "$BINARY" >/dev/null 2>&1 || info "Ad-hoc codesign failed; continuing with unsigned binary."
fi

info "Installing binary to $INSTALL_BIN_DIR/$BIN_NAME"
install -m 755 "$BINARY" "$INSTALL_BIN_DIR/$BIN_NAME"

APP_ROOT=$INSTALL_APP_DIR/$APP_NAME.app
APP_MACOS=$APP_ROOT/Contents/MacOS
APP_RESOURCES=$APP_ROOT/Contents/Resources
mkdir -p "$APP_MACOS" "$APP_RESOURCES"
cat > "$APP_ROOT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.deepclean.deepclean</string>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.9.22</string>
  <key>CFBundleVersion</key><string>0.9.22</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST
cat > "$APP_MACOS/$APP_NAME" <<APP
#!/bin/sh
exec "$INSTALL_BIN_DIR/$BIN_NAME" ui "\$@"
APP
chmod 755 "$APP_MACOS/$APP_NAME"

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$INSTALL_BIN_DIR/$BIN_NAME" "$APP_ROOT" >/dev/null 2>&1 || true
fi
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_ROOT" >/dev/null 2>&1 || info "Ad-hoc app codesign failed; continuing."
fi

"$INSTALL_BIN_DIR/$BIN_NAME" --version >/dev/null || fail "Installed binary smoke test failed."

case ":${PATH:-}:" in
  *":$INSTALL_BIN_DIR:"*) : ;;
  *) info "Add $INSTALL_BIN_DIR to PATH to run '$BIN_NAME' from any terminal." ;;
esac

info "Production install complete:"
info "  CLI: $INSTALL_BIN_DIR/$BIN_NAME"
info "  App: $APP_ROOT"
info "Start Web UI with: open '$APP_ROOT'"
