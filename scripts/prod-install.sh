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
APP_NAME=${APP_NAME:-MacMaid}
BIN_NAME=${BIN_NAME:-macmaid}
INSTALL_BIN_DIR=${INSTALL_BIN_DIR:-$HOME/.local/bin}
INSTALL_APP_DIR=${INSTALL_APP_DIR:-$HOME/Applications}
BUILD_DIR=${BUILD_DIR:-$ROOT/build/prod}
ENTRYPOINT=$BUILD_DIR/macmaid_entry.py
DIST_DIR=$BUILD_DIR/dist
WORK_DIR=$BUILD_DIR/work
SPEC_DIR=$BUILD_DIR/spec
LOGO_PNG=$ROOT/assets/MacMaid-Logo.png
ICONSET=$BUILD_DIR/MacMaid.iconset
ICON_FILE=MacMaid.icns

case "$ROOT" in
  "$HOME"|"$HOME"/*) : ;;
  *) info "Warning: project is outside HOME. If macOS blocks the build, move it under your home directory." ;;
esac

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$ROOT" >/dev/null 2>&1 || true
fi

mkdir -p "$BUILD_DIR" "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR" "$INSTALL_BIN_DIR" "$INSTALL_APP_DIR"
cat > "$ENTRYPOINT" <<'PY'
from macmaid import main

if __name__ == "__main__":
    main()
PY

info "Building standalone MacMaid binary with PyInstaller..."
"$UV" run --python "$PYTHON_VERSION" --with pyinstaller pyinstaller \
  --noconfirm \
  --clean \
  --onefile \
  --name "$BIN_NAME" \
  --distpath "$DIST_DIR" \
  --workpath "$WORK_DIR" \
  --specpath "$SPEC_DIR" \
  --paths "$ROOT/src" \
  --add-data "$ROOT/src/macmaid/WebUI:macmaid/WebUI" \
  --collect-all textual \
  "$ENTRYPOINT"

BINARY=$DIST_DIR/$BIN_NAME
[ -x "$BINARY" ] || fail "PyInstaller did not produce $BINARY"

if command -v codesign >/dev/null 2>&1; then
  info "Applying ad-hoc code signature..."
  codesign --force --sign - "$BINARY" >/dev/null 2>&1 || info "Ad-hoc codesign failed; continuing with unsigned binary."
fi

OLD_COMMAND=$(printf '%s%s' deep clean)
OLD_APP=$(printf '%s%s.app' Deep Clean)
rm -f "$INSTALL_BIN_DIR/$OLD_COMMAND" 2>/dev/null || true
rm -rf "$INSTALL_APP_DIR/$OLD_APP" 2>/dev/null || true
if [ -n "$UV" ]; then "$UV" tool uninstall "$OLD_COMMAND" >/dev/null 2>&1 || true; fi

info "Installing binary to $INSTALL_BIN_DIR/$BIN_NAME"
install -m 755 "$BINARY" "$INSTALL_BIN_DIR/$BIN_NAME"

APP_ROOT=$INSTALL_APP_DIR/$APP_NAME.app
APP_MACOS=$APP_ROOT/Contents/MacOS
APP_RESOURCES=$APP_ROOT/Contents/Resources
mkdir -p "$APP_MACOS" "$APP_RESOURCES"

if [ -f "$LOGO_PNG" ]; then
  cp "$LOGO_PNG" "$APP_RESOURCES/MacMaid-Logo.png"
  if command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
    rm -rf "$ICONSET"
    mkdir -p "$ICONSET"
    sips -z 16 16 "$LOGO_PNG" --out "$ICONSET/icon_16x16.png" >/dev/null
    sips -z 32 32 "$LOGO_PNG" --out "$ICONSET/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$LOGO_PNG" --out "$ICONSET/icon_32x32.png" >/dev/null
    sips -z 64 64 "$LOGO_PNG" --out "$ICONSET/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$LOGO_PNG" --out "$ICONSET/icon_128x128.png" >/dev/null
    sips -z 256 256 "$LOGO_PNG" --out "$ICONSET/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$LOGO_PNG" --out "$ICONSET/icon_256x256.png" >/dev/null
    sips -z 512 512 "$LOGO_PNG" --out "$ICONSET/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$LOGO_PNG" --out "$ICONSET/icon_512x512.png" >/dev/null
    sips -z 1024 1024 "$LOGO_PNG" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
    iconutil -c icns "$ICONSET" -o "$APP_RESOURCES/$ICON_FILE"
    info "App icon generated from assets/MacMaid-Logo.png"
  else
    info "sips/iconutil unavailable; copied PNG logo but skipped .icns generation."
  fi
else
  info "Logo not found at $LOGO_PNG; app icon skipped."
fi

cat > "$APP_ROOT/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>com.macmaid.macmaid</string>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>$ICON_FILE</string>
  <key>CFBundleShortVersionString</key><string>0.9.22</string>
  <key>CFBundleVersion</key><string>0.9.22</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict>
</plist>
PLIST
install -m 755 "$BINARY" "$APP_MACOS/macmaid-bin"

SWIFT_APP_SRC="$ROOT/src/macmaid/native/MacMaidApp.swift"
if command -v swiftc >/dev/null 2>&1 && [ -f "$SWIFT_APP_SRC" ]; then
  info "Compiling native Cocoa/WebKit window wrapper with swiftc..."
  swiftc -O -framework Cocoa -framework WebKit "$SWIFT_APP_SRC" -o "$APP_MACOS/$APP_NAME"
else
  info "swiftc not found; using fallback shell launcher."
  cat > "$APP_MACOS/$APP_NAME" <<APP
#!/bin/sh
exec "$INSTALL_BIN_DIR/$BIN_NAME" ui "\$@"
APP
  chmod 755 "$APP_MACOS/$APP_NAME"
fi

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$INSTALL_BIN_DIR/$BIN_NAME" "$APP_ROOT" >/dev/null 2>&1 || true
fi
if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - "$APP_ROOT" >/dev/null 2>&1 || info "Ad-hoc app codesign failed; continuing."
fi
touch "$APP_ROOT"

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
info "  App: $APP_ROOT"
info "Start Web UI with: open '$APP_ROOT'"
